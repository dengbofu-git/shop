const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../static/js/buyer-support.js'),'utf8');
class Node {
    constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.events={};this.style={};this.isConnected=true;}
    appendChild(node){this.children.push(node);return node;}
    setAttribute(k,v){this.attrs[k]=v;}
    removeAttribute(k){delete this.attrs[k];}
    addEventListener(k,v){this.events[k]=v;}
    getBoundingClientRect(){return {left:20,bottom:90};}
    focus(){this.focused=true;}
    set textContent(v){this.text=v;this.children=[];}
    get textContent(){return this.text;}
}
async function setup(removed=false){
    const list=new Node(),calls=[];
    const c={busy:false,ensureIdentity:()=>true,hiddenHistory:new Set(removed?['one']:[]),showingRemoved:removed,
        historyList:list,historyStatus:new Node(),historyMore:new Node(),historyMenu:new Node(),historyDelete:new Node('button'),
        menuConversation:null,historyCursor:null,historyLoaded:false,displayTime:()=> 'now',updateSession(){},
        setBusy(v){c.busy=v;},document:{createElement:tag=>new Node(tag)},
        window:{innerWidth:375,innerHeight:700},
        async api(){return {conversations:[{conversation_id:'one',title:'测试咨询',updated_at:'now',turn_count:2}],next_cursor:null};},
        switchConversation:id=>calls.push(id),restoreHiddenHistory:id=>calls.push('restore:'+id)};
    c.historyMenu.offsetWidth=144;c.historyMenu.offsetHeight=45;
    vm.createContext(c);
    vm.runInContext(source.slice(source.indexOf('    function closeHistoryMenu('),source.indexOf("    historyDelete.addEventListener('click'"))+
        source.slice(source.indexOf('    async function loadHistory('),source.indexOf('    async function loadOlder(')),c);
    await c.loadHistory(true);
    return {c,list,calls};
}
function descendants(node){return node.children.flatMap(child=>[child,...descendants(child)]);}
test('history provides separate visible chat and menu buttons for touch and keyboard',async()=>{
    const {c,list,calls}=await setup();
    const buttons=descendants(list).filter(n=>n.tag==='button');
    assert.equal(buttons.length,2);
    const menu=buttons.find(n=>n.className==='bs-history-actions');
    assert.match(menu.attrs['aria-label'],/测试咨询/);
    assert.equal(menu.attrs['aria-haspopup'],'menu');
    menu.events.click({preventDefault(){}});
    assert.equal(c.historyMenu.hidden,false);assert.equal(c.menuConversation.id,'one');
    assert.equal(c.historyDelete.focused,true);assert.deepEqual(calls,[]);
    c.closeHistoryMenu(true);assert.equal(menu.focused,true);assert.equal(menu.attrs['aria-expanded'],'false');
    buttons.find(n=>n.className==='bs-history-item').events.click();
    assert.deepEqual(calls,['one']);
    assert(buttons.every(n=>descendants(n).every(child=>child.tag!=='button')));
});
test('removed history exposes restore action without a remove menu',async()=>{
    const {list,calls}=await setup(true);
    const buttons=descendants(list).filter(n=>n.tag==='button');
    assert.equal(buttons.length,1);assert.match(buttons[0].attrs['aria-label'],/恢复咨询/);
    buttons[0].events.click();assert.deepEqual(calls,['restore:one']);
});
