/* Exercise the actual controller with delayed HTTP responses and isolated browser storage. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const path = require('node:path');
const flush = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => {resolve=a; reject=b;}); return {promise,resolve,reject}; };
const row = (id, text) => ({id, text, created_at:'2026-10-22T00:00:00Z', is_mine:false, context:{}});
const history = (id, text='history ' + id) => ({conversation_id:id, name:'Shop ' + id, items:[row(id * 10,text)], has_more:false, other_read_id:0});

class Element {
    constructor(tag='div') {
        this.tag=tag; this.children=[]; this.dataset={}; this.attrs={}; this.events={}; this.hidden=false;
        this.value=''; this.disabled=false; this.scrollTop=0; this.scrollHeight=100; this.clientHeight=100;
        this.classes=new Set(); this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c)};
        this._text='';
    }
    set textContent(value) {this._text=String(value); this.children=[];}
    get textContent() {return this._text + this.children.map(item=>item.textContent).join('');}
    append(...items) {for (const item of items) this.children.push(...(item.tag==='fragment' ? item.children : [item]));}
    prepend(item) {this.children.unshift(...(item.tag==='fragment' ? item.children : [item]));}
    insertBefore(item,next) {if(!next)this.children.push(item); else this.children.splice(this.children.indexOf(next),0,item);}
    replaceChildren(...items) {this._text=''; this.children=[]; this.append(...items);}
    setAttribute(key,value) {this.attrs[key]=value;}
    addEventListener(key,action) {(this.events[key] ||= []).push(action);}
    async emit(key) {for (const action of this.events[key] || []) await action({preventDefault(){}});}
    querySelectorAll(selector) {
        const result=[];
        for (const child of this.children) {
            if ((selector==='[data-own-message]' && child.dataset.ownMessage) ||
                (selector==='[data-message-id]' && child.dataset.messageId) ||
                (selector==='button[data-conversation-id]' && child.tag==='button' && child.dataset.conversationId)) result.push(child);
            result.push(...child.querySelectorAll(selector));
        }
        return result;
    }
    set innerHTML(_) {throw new Error('Unsafe HTML');}
}

async function setup({search='',role='buyer',intercept,items}={}) {
    const ids=['eng-conversations','eng-messages','eng-compose','eng-message-text','eng-status','eng-layout','eng-send','eng-older',
        'eng-chat-title','eng-context','eng-list-pager','eng-back-list','eng-refresh','eng-inbox-hint','eng-page-title'];
    const nodes=Object.fromEntries(ids.map(id=>[id,new Element()])); nodes['eng-compose'].hidden=true;
    const calls=[], storage=new Map(), timers=[], listeners={}, rows=items || [1,2].map(id=>({id,name:'Shop ' + id,unread:0,other_read_id:0,last_text:'Preview ' + id,updated_at:'2026-10-22'}));
    const document={body:{dataset:{engRole:role}},documentElement:{lang:'zh'},hidden:false,hasFocus:()=>true,
        getElementById:id=>nodes[id],querySelectorAll:()=>[],createDocumentFragment:()=>new Element('fragment'),
        addEventListener:(key,fn)=>{listeners[key]=fn;}};
    const location={href:'http://localhost/buyer_messages.html' + search, search, replace(){}};
    let sent=0;
    const E={node:(tag,text,cls)=>{const el=new Element(tag); if(text!=null)el.textContent=text; el.className=cls; return el;},
        t:key=>key, date:value=>value, id:()=> 'synthetic-' + (++sent), pager(){},language:()=> 'zh',updateLanguage(){},
        button:(label,action)=>{const el=new Element('button');el.textContent=label;el.addEventListener('click',action);return el;},
        api:async (url,payload)=>{
            calls.push({url,payload});
            const result=intercept && intercept(url,payload);
            if(result!==undefined)return result;
            if(url==='identity')return {portal:role};
            if(url.startsWith('conversations?page='))return {items:rows,page:1,pages:1,total:rows.length,unread_total:0};
            if(url.startsWith('conversations/resolve'))return {conversation_id:null,merchant_id:2,merchant_name:'Shop 2',context:{}};
            const match=url.match(/^conversations\/(\d+)\/messages/);
            if(match && !payload)return url.includes('after=') ? {...history(Number(match[1])),items:[]} : history(Number(match[1]));
            if(url.endsWith('/read'))return {};
            throw new Error('Unexpected request: ' + url);
        }};
    const window={Engagement:E,frameElement:null,history:{replaceState:(_,__,url)=>{
        location.href='http://localhost' + url; location.search=new URL(location.href).search;
    }},addEventListener:(key,fn)=>{listeners[key]=fn;}};
    const context={window,document,location,URL,URLSearchParams,AuthStorage:{getUser:()=> 'synthetic-buyer'},
        sessionStorage:{getItem:k=>storage.get(k) || null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
        setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},Set,Math,JSON};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/engagement-messages.js'),'utf8'),context);
    await flush();
    return {nodes,calls,storage,location,timers,listeners,select:async id=>{
        const button=nodes['eng-conversations'].children.find(el=>Number(el.dataset.conversationId)===id);
        assert(button,'conversation button missing'); await button.emit('click'); await flush();
    }};
}

test('multiple conversations have distinct labels; selection is restored from URL after refresh',async()=>{
    const app=await setup();
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 1 · #1');
    assert.equal(app.nodes['eng-list-pager'].hidden,true);
    assert(app.nodes['eng-conversations'].textContent.includes('conversation #2'));
    await app.select(2);
    assert.equal(app.location.search,'?conversation_id=2');
    const refreshed=await setup({search:app.location.search});
    assert.equal(refreshed.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
    assert.equal(refreshed.nodes['eng-messages'].textContent.includes('history 1'),false);
    assert(refreshed.nodes['eng-messages'].textContent.includes('history 2'));
});

test('switching conversations discards a delayed history response and prevents sending before history loads',async()=>{
    const old=deferred();
    const app=await setup({intercept:url=>url==='conversations/1/messages' ? old.promise : undefined});
    assert.equal(app.nodes['eng-send'].disabled,true);
    assert.equal(app.nodes['eng-compose'].hidden,true);
    await app.select(2);
    old.resolve(history(1,'OLD CUSTOMER HISTORY')); await flush();
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
    assert.equal(app.nodes['eng-messages'].textContent.includes('OLD CUSTOMER'),false);
    assert.equal(app.nodes['eng-send'].disabled,false);
    assert.equal(app.calls.some(call=>call.url==='conversations/1/read'),false);
});

test('a failed send in one conversation preserves its draft without showing the error in another',async()=>{
    const sending=deferred();
    const app=await setup({intercept:(url,payload)=>url==='conversations/1/messages' && payload ? sending.promise : undefined});
    const area=app.nodes['eng-message-text']; area.value='first customer draft'; await area.emit('input');
    const submitted=app.nodes['eng-compose'].emit('submit');
    await app.select(2);
    sending.reject(new Error('old conversation send failed')); await submitted; await flush();
    assert.equal(app.nodes['eng-status'].textContent,'');
    assert.equal(app.nodes['eng-messages'].textContent.includes('first customer draft'),false);
    await app.select(1);
    assert.equal(area.value,'first customer draft');
    assert(app.storage.get('tea_saas_message_draft:synthetic-buyer:1:pending'));
});

test('first successful send saves the conversation URL, and reload reads history from the API',async()=>{
    const app=await setup({search:'?merchant_id=2',items:[],intercept:(url,payload)=>url==='conversations' && payload ?
        {conversation_id:2,message:{...row(20,payload.text),is_mine:true}} : undefined});
    app.nodes['eng-message-text'].value='persist me'; await app.nodes['eng-compose'].emit('submit');
    assert.equal(app.location.search,'?conversation_id=2');
    assert.equal(app.storage.size,0);
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
    const restored=await setup({search:app.location.search,intercept:url=>url==='conversations/2/messages' ? history(2,'persist me') : undefined});
    assert(restored.nodes['eng-messages'].textContent.includes('persist me'));
});

test('empty merchant inbox explains customer initiation and hides unnecessary pagination',async()=>{
    const app=await setup({role:'merchant',items:[]});
    assert.equal(app.nodes['eng-inbox-hint'].dataset.engText,'merchantChats');
    assert.equal(app.nodes['eng-page-title'].dataset.engText,'consultations');
    assert(app.nodes['eng-conversations'].textContent.includes('emptyMerchantChats'));
    assert.equal(app.nodes['eng-compose'].hidden,true);
    assert.equal(app.nodes['eng-list-pager'].hidden,true);
});

test('a delayed successful send refreshes the inbox without changing the newly selected conversation',async()=>{
    const sending=deferred();
    const app=await setup({intercept:(url,payload)=>url==='conversations/1/messages' && payload ? sending.promise : undefined});
    app.nodes['eng-message-text'].value='message for shop one';
    const submitted=app.nodes['eng-compose'].emit('submit');
    await app.select(2);
    sending.resolve({conversation_id:1,message:row(11,'message for shop one')}); await submitted; await flush();
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
    assert.equal(app.location.search,'?conversation_id=2');
    assert.equal(app.nodes['eng-messages'].textContent.includes('message for shop one'),false);
    assert.equal(app.nodes['eng-send'].disabled,false);
});

test('background refreshes cannot overwrite a newer conversation list response',async()=>{
    const stale=deferred(); let listRequests=0;
    const app=await setup({intercept:url=>{
        if(url.startsWith('conversations?page=') && ++listRequests===3)return stale.promise;
    }});
    const refresh=app.listeners['eng:language']; refresh(); await flush();
    stale.resolve({items:[{id:99,name:'STALE SHOP',unread:0,other_read_id:0,last_text:'old',updated_at:'2026-10-22'}],page:1,pages:1});
    await flush();
    assert.equal(app.nodes['eng-conversations'].textContent.includes('STALE SHOP'),false);
    assert(app.nodes['eng-conversations'].textContent.includes('Shop 2'));
});

test('history failure hides composer and refresh recovers the same saved conversation',async()=>{
    let fail=true;
    const app=await setup({search:'?conversation_id=2',intercept:url=>url==='conversations/2/messages' && fail ?
        Promise.reject(new Error('history unavailable')) : undefined});
    assert.equal(app.nodes['eng-compose'].hidden,true);
    app.nodes['eng-message-text'].value='do not send blindly';
    await app.nodes['eng-compose'].emit('submit');
    assert.equal(app.calls.some(call=>call.payload && call.payload.text),false);
    fail=false; app.nodes['eng-refresh'].onclick(); await flush();
    assert.equal(app.nodes['eng-compose'].hidden,false);
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
    assert.equal(app.nodes['eng-status'].textContent,'');
});

test('a local send cannot skip an incoming message that was committed before the send response',async()=>{
    let sent=false;
    const app=await setup({intercept:(url,payload)=>{
        if(url==='conversations/1/messages' && payload){sent=true;return {conversation_id:1,message:{...row(12,'own message'),is_mine:true}};}
        if(sent && url==='conversations/1/messages?after=10')return {...history(1),items:[row(11,'incoming between polls'),{...row(12,'own message'),is_mine:true}]};
    }});
    app.nodes['eng-message-text'].value='own message'; await app.nodes['eng-compose'].emit('submit');
    await app.timers[app.timers.length-1](); await flush();
    const messages=app.nodes['eng-messages'].children;
    assert.deepEqual(messages.map(el=>el.dataset.messageId),[10,11,12]);
    assert.equal(messages.filter(el=>el.textContent.includes('own message')).length,1);
    assert(messages[1].textContent.includes('incoming between polls'));
});

test('read receipts stop at fetched history rather than jumping over unseen messages to a local send',async()=>{
    let sent=false;
    const app=await setup({intercept:(url,payload)=>{
        if(url==='conversations/1/messages' && payload){sent=true;return {conversation_id:1,message:{...row(99,'own later message'),is_mine:true}};}
        if(sent && url==='conversations/1/messages?after=10')return {...history(1),has_more:true,items:[row(11,'first incoming page')]};
    }});
    app.nodes['eng-message-text'].value='own later message'; await app.nodes['eng-compose'].emit('submit');
    await app.timers[app.timers.length-1](); await flush();
    const receipts=app.calls.filter(call=>call.url==='conversations/1/read');
    assert.equal(receipts[receipts.length-1].payload.message_id,11);
    assert.equal(receipts.some(call=>call.payload.message_id===99),false);
});


test('nickname change refreshes active list and title while duplicate names retain distinct IDs',async()=>{
    const items=[1,2].map(id=>({id,name:'同名茶友',unread:0,other_read_id:0,last_text:'message',updated_at:'2026-10-22'}));
    const app=await setup({role:'merchant',items,intercept:url=>url==='conversations/1/messages' ? {...history(1),name:items[0].name}:undefined});
    items[0].name='<img src=x onerror=alert(1)>';
    await app.timers[app.timers.length-1]();await flush();
    assert.equal(app.nodes['eng-chat-title'].textContent,items[0].name+' · #1');
    assert(app.nodes['eng-conversations'].textContent.includes(items[0].name));
    assert(app.nodes['eng-conversations'].textContent.includes('conversation #2'));
});
