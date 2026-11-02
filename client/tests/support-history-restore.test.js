const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../static/js/buyer-support.js'),'utf8');
const actions=source.slice(source.indexOf("    historyDelete.addEventListener('click'"),source.indexOf("    historyMenu.addEventListener('keydown'"));
function setup(fail=false) {
    const calls=[], events={}, rows=[{dataset:{conversationId:'saved'},remove(){rows.splice(rows.indexOf(this),1);}}];
    function button(id){return {hidden:false,textContent:'',addEventListener(e,f){events[id+':'+e]=f;}};}
    const stored=new Map();let identity=true;
    const c={menuConversation:{id:'saved'},busy:false,hiddenHistory:new Set(),lastRemoved:null,
        showingRemoved:false,hiddenHistoryKey:'support-hidden-history:buyerA',drafts:{},conversation:{conversation_id:'saved'},
        historyDelete:button('remove'),historyUndo:button('undo'),historyRemoved:button('removed'),
        historyList:{children:rows,querySelectorAll:()=>rows.slice()},historyStatus:{textContent:''},
        conversationStatus:{textContent:''},historyRefresh:{focus(){}},input:{value:'draft'},messages:{innerHTML:'record'},
        initialMessage:'new',storageKey:'support-conversation:buyerA',historyCursor:null,
        localStorage:{setItem(k,v){if(fail)throw Error('quota');stored.set(k,v);}},
        sessionStorage:{getItem:()=>null,removeItem(){}},
        ensureIdentity:()=>identity,sameIdentity:()=>identity,closeHistoryMenu(){},saveDraft(){},updateSession(){},
        setBusy(v){c.busy=v;},async loadHistory(reset){calls.push(reset);return true;},
        fetch(){throw Error('History removal must not write server records');}};
    vm.createContext(c);vm.runInContext(actions,c);
    return {c,rows,stored,calls,events,setIdentity:v=>{identity=v;}};
}
test('remove is browser-only and undo persists restoration before refreshing history',async()=>{
    const a=setup();await a.events['remove:click']();
    assert(a.c.hiddenHistory.has('saved'));assert.equal(a.rows.length,0);
    assert.equal(a.stored.get('support-hidden-history:buyerA'),'["saved"]');
    assert.equal(a.c.historyUndo.hidden,false);
    await a.c.restoreHiddenHistory('saved');
    assert.equal(a.c.hiddenHistory.size,0);assert.equal(a.stored.get('support-hidden-history:buyerA'),'[]');
    assert.deepEqual(a.calls,[true]);assert.equal(a.c.historyUndo.hidden,true);
});
test('quota failure keeps visible row, active conversation and current input',async()=>{
    const a=setup(true);await a.events['remove:click']();
    assert.equal(a.rows.length,1);assert.equal(a.c.hiddenHistory.size,0);
    assert.equal(a.c.conversation.conversation_id,'saved');assert.equal(a.c.input.value,'draft');
    assert.match(a.c.historyStatus.textContent,/仍保留/);
});
test('identity changes reject removal and removed-view toggling',async()=>{
    const a=setup();a.setIdentity(false);await a.events['remove:click']();a.events['removed:click']();
    assert.equal(a.stored.size,0);assert.equal(a.c.showingRemoved,false);assert.equal(a.rows.length,1);
});
test('removed view and restoration use the existing paged read flow',async()=>{
    const a=setup();a.events['removed:click']();assert.equal(a.c.showingRemoved,true);
    assert.equal(a.c.historyRemoved.textContent,'返回历史咨询');
    a.events['removed:click']();assert.equal(a.c.showingRemoved,false);assert.deepEqual(a.calls,[true,true]);
});

test('failed restoration keeps the hidden identifier and offers retry',async()=>{
    const a=setup(true);a.c.hiddenHistory.add('saved');a.c.lastRemoved='saved';
    await a.events['undo:click']();
    assert(a.c.hiddenHistory.has('saved'));assert.equal(a.c.lastRemoved,'saved');
    assert.equal(a.calls.length,0);assert.match(a.c.historyStatus.textContent,/重试/);
});

test('history reload failure does not claim the restored conversation is visible',async()=>{
    const a=setup();a.c.hiddenHistory.add('saved');a.c.lastRemoved='saved';
    a.c.loadHistory=async()=>{a.c.historyStatus.textContent='网络中断，请重试';return false;};
    await a.c.restoreHiddenHistory('saved');
    assert(!a.c.hiddenHistory.has('saved'));
    assert.match(a.c.historyStatus.textContent,/网络中断/);
    assert.doesNotMatch(a.c.historyStatus.textContent,/已恢复到历史列表/);
});

test('account changes during reload cannot write a restoration success message',async()=>{
    const a=setup();a.c.lastRemoved='saved';
    a.c.loadHistory=async()=>{a.setIdentity(false);a.c.historyStatus.textContent='账号已切换';return true;};
    await a.c.restoreHiddenHistory('saved');
    assert.equal(a.c.historyStatus.textContent,'账号已切换');
});
