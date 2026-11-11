"""CourtLab web app; /chat retains Project 1's response/session_id/tool_calls contract."""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from litellm import RateLimitError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

HERE=Path(__file__).parent
load_dotenv(HERE/'.env')
import store
from context_panel import AgentContexts, PanelHooks, add_context_panel
from research import RunState, deep_research
from web_sources import search_available

app=FastAPI(title='CourtLab')
sessions={}
chats={}
add_context_panel(app,sessions)
capacity=asyncio.Semaphore(3)
TIMEOUT=240
MAX_SESSIONS=100

class ChatInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(min_length=1,max_length=8000)
    session_id:str|None=Field(default=None,min_length=1,max_length=100)

def reply(text,session_id=None,traces=None,**extra):
    return {'response':text,'session_id':session_id,'tool_calls':traces or [],**extra}

@app.exception_handler(Exception)
async def unexpected(request,exc):
    logging.exception('Request failed',exc_info=exc)
    return JSONResponse(reply('The request could not finish. Please retry.'),status_code=500)

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def invalid_input(request,exc):
    return JSONResponse(reply('Send a JSON object with a nonempty message of at most 8,000 characters and optional session_id.'),status_code=400)

@app.get('/')
def index(): return FileResponse(HERE/'index.html',headers={'Cache-Control':'no-cache'})
@app.get('/app.js')
def script(): return FileResponse(HERE/'app.js',media_type='application/javascript',headers={'Cache-Control':'no-cache'})
@app.get('/style.css')
def style(): return FileResponse(HERE/'style.css',media_type='text/css',headers={'Cache-Control':'no-cache'})
@app.get('/health')
def health(): return {'ok':store.DB.exists(),'service':'courtlab','database_ready':store.DB.exists()}
@app.get('/catalog')
def catalog(): return {**store.catalog(),'web_search_available':search_available()}
@app.get('/manifest')
def manifest(): return json.loads((HERE/'data/manifest.json').read_text())
@app.get('/evidence/{source_id}')
def evidence(source_id:str):
    item=store.evidence(source_id)
    return JSONResponse(item,status_code=404 if 'error' in item else 200)
@app.get('/sessions/{session_id}')
def history(session_id:str):
    chat=chats.get(session_id)
    if not chat: return JSONResponse(reply('Session expired; start a new chat.'),status_code=404)
    return {'session_id':session_id,'messages':chat['history']}
@app.delete('/sessions/{session_id}')
def delete_session(session_id:str):
    chat=chats.get(session_id)
    if chat and chat['lock'].locked():
        return JSONResponse(reply('Research is still running.',session_id),status_code=409)
    chats.pop(session_id,None); sessions.pop(session_id,None)
    return {'ok':True,'session_id':session_id}

def resolve(data):
    if not data.message.strip(): return None,JSONResponse(reply('Enter a research question.'),status_code=400)
    now=time.time()
    for sid in list(chats):
        if now-chats[sid]['updated']>3600 and not chats[sid]['lock'].locked():
            chats.pop(sid);sessions.pop(sid,None)
    if data.session_id:
        if data.session_id not in chats:
            return None,JSONResponse(reply('Session expired; start a new chat.'),status_code=404)
        sid=data.session_id
    else:
        if len(chats)>=MAX_SESSIONS:
            return None,JSONResponse(reply('Server session capacity reached; try again later.'),status_code=503)
        sid=str(uuid4())
        chats[sid]={'history':[],'lock':asyncio.Lock(),'updated':now}
    if chats[sid]['lock'].locked():
        return None,JSONResponse(reply('A question is already running in this chat.',sid),status_code=409)
    if len(chats[sid]['history'])>=40:
        return None,JSONResponse(reply('This chat reached its turn limit. Start a new chat.',sid),status_code=409)
    return sid,None

async def perform(data,sid,emit):
    chat=chats[sid]
    async with chat['lock']:
        # New contexts for every research run. Only bounded chat history reaches the Lead.
        sessions[sid]=AgentContexts()
        hooks=PanelHooks(sessions[sid],emit)
        state=RunState(hooks)
        context={'latest_question':data.message.strip(),'prior_conversation':[
            {'role':m['role'],'content':m['content']} for m in chat['history'][-8:]]}
        try:
            async with asyncio.timeout(TIMEOUT):
                async with capacity:
                    answer,meta=await deep_research(json.dumps(context,ensure_ascii=False),state)
            result=reply(answer,sid,state.traces,research=meta)
            chat['history'] += [{'role':'user','content':data.message.strip()},
                {'role':'assistant','content':answer,'tool_calls':state.traces,'research':meta}]
            code=200
        except RateLimitError:
            result=reply('The research model is temporarily busy. Please wait a moment and retry. Your earlier conversation is preserved.',sid,state.traces,research={'status':'rate_limited'})
            code=429
        except TimeoutError:
            result=reply('Research reached its four-minute limit. Narrow the question and retry. Partial tool results are preserved below.',sid,state.traces,research={'status':'timeout'})
            code=504
        except Exception:
            logging.exception('Research run failed')
            result=reply('Research could not finish. Check model access, Google Cloud credentials and quota, then retry.',sid,state.traces,research={'status':'error'})
            code=502
        chat['updated']=time.time()
        return result,code

@app.post('/chat')
async def chat(data:ChatInput):
    sid,error=resolve(data)
    if error:return error
    result,code=await perform(data,sid,lambda event:None)
    return JSONResponse(result,status_code=code)

@app.post('/run')
async def run(data:ChatInput,request:Request):
    sid,error=resolve(data)
    if error:return error
    queue=asyncio.Queue()
    async def work():
        result,code=await perform(data,sid,queue.put_nowait)
        queue.put_nowait({'type':'done','status_code':code,**result})
    task=asyncio.create_task(work())
    async def events():
        try:
            yield 'data: '+json.dumps({'type':'start','session_id':sid})+'\n\n'
            while True:
                try: event=await asyncio.wait_for(queue.get(),timeout=10)
                except TimeoutError:
                    yield ': keepalive\n\n'; continue
                yield 'data: '+json.dumps(event,ensure_ascii=False,default=str)+'\n\n'
                if event['type']=='done':break
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
    return StreamingResponse(events(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=int(os.getenv('PORT','8080')))
