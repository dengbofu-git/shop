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

test('left-button drag moves a conversation and keeps the active chat without triggering a click',async()=>{
    const app=await setup(), list=app.nodes['eng-conversations'];
    const [first,second]=list.children, originalChat=app.nodes['eng-messages'].textContent;
    const transfer={setData(type,id){assert.equal(type,'text/plain');assert.equal(id,'1');}};
    await first.emit('dragstart',{dataTransfer:transfer});
    assert.equal(first.classList.contains('eng-dragging'),true);
    await second.emit('dragover',{clientY:second.getBoundingClientRect().bottom-1});
    assert.deepEqual(list.children.map(item=>Number(item.dataset.conversationId)),[2,1]);
    await list.emit('drop'); await first.emit('dragend');
    assert.equal(first.classList.contains('eng-dragging'),false);
    assert.equal(app.nodes['eng-messages'].textContent,originalChat);
    assert.equal(app.location.search,'?conversation_id=1');
    assert.deepEqual(JSON.parse(app.persisted.get('tea_saas_conversation_order:buyer:synthetic-buyer')),[2,1]);
    await app.select(2);
    assert.equal(app.location.search,'?conversation_id=1','release click must not select a chat');
    const refreshed=await setup({persisted:app.persisted});
    assert.deepEqual(refreshed.nodes['eng-conversations'].children.map(item=>Number(item.dataset.conversationId)),[2,1]);
});

test('polling keeps dragged cards stable and cancelled drags restore the original sequence',async()=>{
    const app=await setup(), list=app.nodes['eng-conversations'], [first,second]=list.children;
    await first.emit('dragstart');
    await second.emit('dragover',{clientY:second.getBoundingClientRect().bottom-1});
    app.listeners['eng:language'](); await flush();
    assert.deepEqual(list.children,[second,first]);
    app.listeners.keydown({key:'Escape',preventDefault(){}});
    assert.deepEqual(list.children,[first,second]);
    assert.equal(app.persisted.size,0);
    await first.emit('dragend');
    assert.deepEqual(list.children,[first,second]);
});

test('keyboard reorder persists independently for each account and role',async()=>{
    const persisted=new Map();
    const app=await setup({persisted});
    await app.nodes['eng-conversations'].children[0].emit('keydown',{key:'ArrowDown',altKey:true});
    assert.equal(app.nodes['eng-status'].textContent,'conversationOrderSaved');
    app.listeners['eng:language'](); await flush();
    assert.deepEqual(app.nodes['eng-conversations'].children.map(item=>Number(item.dataset.conversationId)),[2,1]);
    const merchant=await setup({persisted,role:'merchant'}), other=await setup({persisted,user:'another-buyer'});
    for(const isolated of [merchant,other])assert.deepEqual(isolated.nodes['eng-conversations'].children.map(item=>Number(item.dataset.conversationId)),[1,2]);
});

test('dropping outside the list cancels sorting and prevents inserting an ID into the draft',async()=>{
    const app=await setup(), list=app.nodes['eng-conversations'], [first,second]=list.children;
    app.nodes['eng-message-text'].value='keep this question';
    await first.emit('dragstart');
    await second.emit('dragover',{clientY:second.getBoundingClientRect().bottom-1});
    const event={target:app.nodes['eng-message-text'],preventDefault(){this.defaultPrevented=true;}};
    app.listeners.drop(event);
    assert.equal(event.defaultPrevented,true);
    assert.deepEqual(list.children,[first,second]);
    assert.equal(app.nodes['eng-message-text'].value,'keep this question');
    assert.equal(app.persisted.size,0);
});

test('sorting a later page retains preceding page positions in the global preference',async()=>{
    const rows=[1,2,3,4].map(id=>({id,name:'Shop '+id,last_text:'',updated_at:'2026-10-22',other_read_id:0}));
    const app=await setup({intercept:url=>{
        if(!url.startsWith('conversations?page='))return;
        const page=Number(new URL('http://localhost/'+url).searchParams.get('page'));
        return {items:rows.slice((page-1)*2,page*2),page,pages:2,total:4};
    }});
    app.nodes['eng-list-pager'].changePage(2); await flush();
    await app.nodes['eng-conversations'].children[0].emit('keydown',{key:'ArrowDown',altKey:true});
    assert.deepEqual(JSON.parse(app.persisted.get('tea_saas_conversation_order:buyer:synthetic-buyer')),[1,2,4,3]);
});

test('unavailable browser storage reports unsaved order and does not break the inbox',async()=>{
    const app=await setup({persisted:{get(){throw new Error('blocked');},set(){throw new Error('blocked');}}});
    await app.nodes['eng-conversations'].children[0].emit('keydown',{key:'ArrowDown',altKey:true});
    assert.equal(app.nodes['eng-status'].textContent,'conversationOrderNotSaved');
    assert.equal(app.nodes['eng-compose'].hidden,false);
});

test('right-click offers participant-local hiding, clamps menu and clears active chat and URL',async()=>{
    const app=await setup();
    app.nodes['eng-message-text'].value='saved unsent question';
    await app.nodes['eng-message-text'].emit('input');
    const card=app.nodes['eng-conversations'].children[0];
    const event=await card.emit('contextmenu',{clientX:999,clientY:699});
    assert.equal(event.defaultPrevented,true);
    const menu=app.nodes['eng-conversation-menu'];
    assert.equal(menu.hidden,false);
    assert.equal(menu.style.left,'772px');
    assert.equal(menu.style.top,'592px');
    assert.equal(app.nodes['eng-hide-conversation'].focused,true);
    await app.nodes['eng-hide-conversation'].emit('click');
    assert(app.calls.some(call=>call.url==='conversations/1/hide' && call.payload));
    assert.equal(menu.hidden,true);
    assert.equal(app.nodes['eng-compose'].hidden,true);
    assert.equal(app.nodes['eng-messages'].textContent,'');
    assert.equal(app.location.search,'');
    assert.equal(app.nodes['eng-conversations'].children.length,1);
    assert.equal(Number(app.nodes['eng-conversations'].children[0].dataset.conversationId),2);
    // Unsent drafts survive hiding so that reopening can continue editing.
    assert.equal(app.storage.get('tea_saas_message_draft:synthetic-buyer:1'),'saved unsent question');
    assert.equal(app.nodes['eng-status'].textContent,'conversationHidden');
});

test('keyboard menu Escape restores focus; outside click closes without hiding',async()=>{
    const app=await setup({role:'merchant'}), card=app.nodes['eng-conversations'].children[1];
    assert.equal((await card.emit('keydown',{key:'F10',shiftKey:true})).defaultPrevented,true);
    await app.nodes['eng-conversation-menu'].emit('keydown',{key:'Escape'});
    assert.equal(card.focused,true);
    assert.equal(app.nodes['eng-conversation-menu'].hidden,true);
    await card.emit('keydown',{key:'ContextMenu'});
    app.listeners.pointerdown({target:new Element()});
    assert.equal(app.nodes['eng-conversation-menu'].hidden,true);
    assert.equal(app.calls.some(call=>call.url.endsWith('/hide')),false);
});

test('hiding another chat preserves current chat; failed hide keeps list and draft',async()=>{
    const app=await setup({intercept:url=>url==='conversations/1/hide' ? Promise.reject(new Error('offline')) : undefined});
    app.nodes['eng-message-text'].value='unsent tea question';
    await app.nodes['eng-conversations'].children[0].emit('contextmenu',{clientX:20,clientY:20});
    await app.nodes['eng-hide-conversation'].emit('click');
    assert.equal(app.nodes['eng-status'].textContent,'offline');
    assert.equal(app.nodes['eng-message-text'].value,'unsent tea question');
    assert.equal(app.nodes['eng-conversations'].children.length,2);
    assert.equal(app.nodes['eng-compose'].hidden,false);
    await app.nodes['eng-conversations'].children[1].emit('contextmenu',{clientX:20,clientY:20});
    await app.nodes['eng-hide-conversation'].emit('click');
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 1 · #1');
    assert.equal(app.nodes['eng-compose'].hidden,false);
    assert.equal(app.nodes['eng-message-text'].value,'unsent tea question');
});

test('late history cannot revive the chat after hiding',async()=>{
    const delayed=deferred(); let requests=0;
    const app=await setup({intercept:url=>url==='conversations/1/messages' && ++requests===2 ? delayed.promise : undefined});
    app.nodes['eng-refresh'].onclick(); await flush();
    await app.nodes['eng-conversations'].children[0].emit('contextmenu',{clientX:20,clientY:20});
    await app.nodes['eng-hide-conversation'].emit('click');
    delayed.resolve(history(1)); await flush();
    assert.equal(app.nodes['eng-messages'].textContent,'');
    assert.equal(app.nodes['eng-compose'].hidden,true);
    assert.equal(app.location.search,'');
});

test('product contact explicitly restores an existing conversation before reading history',async()=>{
    const app=await setup({search:'?sku_id=8',intercept:url=>url.startsWith('conversations/resolve') ?
        {conversation_id:2,merchant_id:20,merchant_name:'Shop 2',context:{}} : undefined});
    const restore=app.calls.findIndex(call=>call.url==='conversations/2/restore');
    const messages=app.calls.findIndex(call=>call.url==='conversations/2/messages');
    assert(restore>=0 && messages>restore);
    assert.equal(app.nodes['eng-chat-title'].textContent,'Shop 2 · #2');
});

test('a hidden conversation in an old URL is cleared without implicit restore',async()=>{
    const error=new Error('hidden on another device'); error.code='CONVERSATION_HIDDEN';
    const app=await setup({search:'?conversation_id=1',intercept:url=>url==='conversations/1/messages' ? Promise.reject(error) : undefined});
    assert.equal(app.location.search,'');
    assert.equal(app.nodes['eng-compose'].hidden,true);
    assert.equal(app.nodes['eng-messages'].textContent,'');
    assert.equal(app.calls.some(call=>call.url.endsWith('/restore')),false);
});

test('successful hiding removes the card even if refreshing the list then fails',async()=>{
    let hidden=false;
    const app=await setup({intercept:url=>{
        if(url==='conversations/1/hide'){hidden=true;return {};}
        if(hidden && url.startsWith('conversations?page='))return Promise.reject(new Error('list offline'));
    }});
    await app.nodes['eng-conversations'].children[0].emit('contextmenu',{clientX:20,clientY:20});
    await app.nodes['eng-hide-conversation'].emit('click');
    assert.equal(app.nodes['eng-conversations'].children.length,1);
    assert.equal(Number(app.nodes['eng-conversations'].children[0].dataset.conversationId),2);
    assert.equal(app.nodes['eng-compose'].hidden,true);
    assert.equal(app.nodes['eng-status'].textContent,'list offline');
});

class Element {
    constructor(tag='div') {
        this.tag=tag; this.children=[]; this.dataset={}; this.attrs={}; this.events={}; this.hidden=false;
        this.value=''; this.disabled=false; this.scrollTop=0; this.scrollHeight=100; this.clientHeight=100;
        this.classes=new Set(); this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c)};
        this._text=''; this.style={};
    }
    set textContent(value) {this._text=String(value); this.children=[];}
    get textContent() {return this._text + this.children.map(item=>item.textContent).join('');}
    detach() {if(this.parent){const index=this.parent.children.indexOf(this);if(index>=0)this.parent.children.splice(index,1);this.parent=null;}}
    append(...items) {for (const item of items) {if(item.tag==='fragment'){this.append(...item.children);continue;}item.detach();item.parent=this;this.children.push(item);}}
    prepend(item) {this.children.unshift(...(item.tag==='fragment' ? item.children : [item]));}
    insertBefore(item,next) {if(item===next)return;item.detach();item.parent=this;if(!next)this.children.push(item); else this.children.splice(this.children.indexOf(next),0,item);}
    replaceChildren(...items) {this._text=''; this.children=[]; this.append(...items);}
    setAttribute(key,value) {this.attrs[key]=value;}
    contains(item) {return this===item || this.children.some(child=>child.contains(item));}
    focus() {this.focused=true;}
    getBoundingClientRect() {const top=30+(this.parent?this.parent.children.indexOf(this)*110:0);return {left:20,top,bottom:top+100,width:220,height:100};}
    addEventListener(key,action) {(this.events[key] ||= []).push(action);}
    async emit(key, init={}) {
        const event={defaultPrevented:false,preventDefault(){this.defaultPrevented=true;},...init};
        for (const action of this.events[key] || []) await action(event);
        return event;
    }
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

async function setup({search='',role='buyer',intercept,items,persisted=new Map(),user='synthetic-buyer'}={}) {
    const ids=['eng-conversations','eng-messages','eng-compose','eng-message-text','eng-status','eng-layout','eng-send','eng-older',
        'eng-chat-title','eng-context','eng-list-pager','eng-back-list','eng-refresh','eng-inbox-hint','eng-page-title',
        'eng-conversation-menu','eng-hide-conversation'];
    const nodes=Object.fromEntries(ids.map(id=>[id,new Element()])); nodes['eng-compose'].hidden=true;
    nodes['eng-conversation-menu'].hidden=true;
    nodes['eng-conversation-menu'].append(nodes['eng-hide-conversation']);
    const submissions=[];
    nodes['eng-compose'].requestSubmit=submitter=>{submissions.push(submitter);nodes['eng-compose'].emit('submit');};
    const calls=[], storage=new Map(), timers=[], listeners={}, hidden=new Set(), rows=items || [1,2].map(id=>({id,name:'Shop ' + id,unread:0,other_read_id:0,last_text:'Preview ' + id,updated_at:'2026-10-22'}));
    const document={body:{dataset:{engRole:role}},documentElement:{lang:'zh'},hidden:false,hasFocus:()=>true,
        getElementById:id=>nodes[id],querySelectorAll:()=>[],createDocumentFragment:()=>new Element('fragment'),
        addEventListener:(key,fn)=>{listeners[key]=fn;}};
    const location={href:'http://localhost/buyer_messages.html' + search, search, replace(){}};
    let sent=0;
    const E={node:(tag,text,cls)=>{const el=new Element(tag); if(text!=null)el.textContent=text; el.className=cls; return el;},
        t:key=>key, date:value=>value, id:()=> 'synthetic-' + (++sent), pager:(host,page,pages,change)=>{host.changePage=change;},language:()=> 'zh',updateLanguage(){},
        button:(label,action)=>{const el=new Element('button');el.textContent=label;el.addEventListener('click',action);return el;},
        api:async (url,payload)=>{
            calls.push({url,payload});
            const result=intercept && intercept(url,payload);
            if(result!==undefined)return result;
            if(url==='identity')return {portal:role};
            if(url.startsWith('conversations?page=')){
                const order=(new URL('http://localhost/'+url).searchParams.get('order') || '').split(',').map(Number);
                const rank=id=>order.includes(id)?order.indexOf(id):order.length;
                return {items:rows.filter(row=>!hidden.has(row.id)).sort((a,b)=>rank(a.id)-rank(b.id)),page:1,pages:1,total:rows.length-hidden.size,unread_total:0};
            }
            const action=url.match(/^conversations\/(\d+)\/(hide|restore)$/);
            if(action){if(action[2]==='hide')hidden.add(Number(action[1]));else hidden.delete(Number(action[1]));return {};}
            if(url.startsWith('conversations/resolve'))return {conversation_id:null,merchant_id:2,merchant_name:'Shop 2',context:{}};
            const match=url.match(/^conversations\/(\d+)\/messages/);
            if(match && !payload)return url.includes('after=') ? {...history(Number(match[1])),items:[]} : history(Number(match[1]));
            if(url.endsWith('/read'))return {};
            throw new Error('Unexpected request: ' + url);
        }};
    const window={Engagement:E,frameElement:null,innerWidth:1000,innerHeight:700,matchMedia:()=>({matches:false}),history:{replaceState:(_,__,url)=>{
        location.href='http://localhost' + url; location.search=new URL(location.href).search;
    }},addEventListener:(key,fn)=>{listeners[key]=fn;}};
    const context={window,document,location,URL,URLSearchParams,AuthStorage:{getUser:()=>user},
        localStorage:{getItem:k=>persisted.get(k)||null,setItem:(k,v)=>persisted.set(k,v)},
        sessionStorage:{getItem:k=>storage.get(k) || null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
        setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},Set,Math,JSON};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/js/engagement-messages.js'),'utf8'),context);
    await flush();
    return {nodes,calls,storage,persisted,location,timers,listeners,submissions,select:async id=>{
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

test('Enter submits through the existing send form for both buyer and merchant',async()=>{
    for(const role of ['buyer','merchant']) {
        const app=await setup({role,intercept:(url,payload)=>payload && payload.text ?
            {conversation_id:1,message:{...row(11,payload.text),is_mine:true}} : undefined});
        const area=app.nodes['eng-message-text'];area.value='  键盘发送  ';
        const event=await area.emit('keydown',{key:'Enter'});await flush();
        assert.equal(event.defaultPrevented,true);
        assert.equal(app.submissions.length,1);assert.equal(app.submissions[0],app.nodes['eng-send']);
        const sent=app.calls.filter(call=>call.payload && call.payload.text);
        assert.equal(sent.length,1);assert.equal(sent[0].url,'conversations/1/messages');
        assert.equal(sent[0].payload.text,'键盘发送');assert.equal(area.value,'');
        assert(app.nodes['eng-messages'].textContent.includes('键盘发送'));
    }
});

test('Enter can send the first product inquiry and persist its conversation selection',async()=>{
    const app=await setup({items:[],search:'?sku_id=130',intercept:(url,payload)=>url==='conversations' && payload ?
        {conversation_id:2,message:{...row(20,payload.text),is_mine:true}} : undefined});
    app.nodes['eng-message-text'].value='第一条消息';
    await app.nodes['eng-message-text'].emit('keydown',{key:'Enter'});await flush();
    const sent=app.calls.find(call=>call.url==='conversations' && call.payload);
    assert(sent);assert.equal(sent.payload.sku_id,'130');assert.equal(sent.payload.text,'第一条消息');
    assert.equal(app.location.search,'?conversation_id=2');assert.equal(app.storage.size,0);
});

test('Shift+Enter retains native newlines and IME confirmation never sends a message',async()=>{
    const app=await setup(),area=app.nodes['eng-message-text'];area.value='正在输入';
    assert.equal((await area.emit('keydown',{key:'Enter',shiftKey:true})).defaultPrevented,false);
    await area.emit('compositionstart');
    assert.equal((await area.emit('keydown',{key:'Enter'})).defaultPrevented,false);
    await area.emit('compositionend');
    assert.equal((await area.emit('keydown',{key:'Enter',isComposing:true})).defaultPrevented,false);
    assert.equal((await area.emit('keydown',{key:'Enter',keyCode:229})).defaultPrevented,false);
    await flush();assert.equal(app.submissions.length,0);
    assert.equal(app.calls.some(call=>call.payload && call.payload.text),false);
    assert.equal(area.value,'正在输入');
});

test('held Enter and repeated key presses during an in-flight send do not duplicate the message',async()=>{
    const sending=deferred();
    const app=await setup({intercept:(url,payload)=>payload && payload.text ? sending.promise : undefined});
    const area=app.nodes['eng-message-text'];area.value='发送一次';
    await area.emit('keydown',{key:'Enter'});
    await area.emit('keydown',{key:'Enter',repeat:true});
    await area.emit('keydown',{key:'Enter'});
    assert.equal(app.submissions.length,1);
    assert.equal(app.calls.filter(call=>call.payload && call.payload.text).length,1);
    sending.resolve({conversation_id:1,message:{...row(11,'发送一次'),is_mine:true}});await flush();
    area.value='长按结束前的新草稿';
    assert.equal((await area.emit('keydown',{key:'Enter',repeat:true})).defaultPrevented,true);
    assert.equal(app.submissions.length,1);assert.equal(area.value,'长按结束前的新草稿');
});

test('Enter does not send whitespace, hidden composers or conversations still loading history',async()=>{
    const app=await setup(),area=app.nodes['eng-message-text'];
    for(const text of ['', '  \n  ']) {area.value=text;await area.emit('keydown',{key:'Enter'});}
    app.nodes['eng-compose'].hidden=true;area.value='hidden';await area.emit('keydown',{key:'Enter'});
    assert.equal(app.submissions.length,0);
    const waiting=deferred(),loading=await setup({intercept:url=>url==='conversations/1/messages' ? waiting.promise : undefined});
    loading.nodes['eng-message-text'].value='history pending';
    await loading.nodes['eng-message-text'].emit('keydown',{key:'Enter'});
    assert.equal(loading.submissions.length,0);
    waiting.resolve(history(1));await flush();
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
