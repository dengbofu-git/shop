const {test}=require('node:test');
const assert=require('node:assert/strict');
const {normalized,createController,mount}=require('../static/js/profile-nickname.js');
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('nickname validation counts Unicode characters, allows clearing and rejects controls',()=>{
    assert.equal(normalized('  茶友🍃  '),'茶友🍃');assert.equal(normalized('   '),'');
    assert.equal(normalized('🍵'.repeat(30)),'🍵'.repeat(30));
    for(const value of ['🍵'.repeat(31),'茶\n友','茶\u0000友',null,12])assert.throws(()=>normalized(value));
});
test('save and clear send display data without changing login identity',async()=>{
    const states=[],calls=[],identity={username:'account',token:'synthetic'};
    const c=createController({identity:()=>identity,onState:s=>states.push(s),request:async(who,name)=>{calls.push({who:{...who},name});return {code:200,data:{nickname:name}};}});
    await c.save('  茶友  ');assert.equal(states.at(-1).nickname,'茶友');
    await c.save('');assert.equal(states.at(-1).message,'cleared');
    assert.equal(calls[0].who.username,'account');assert.deepEqual(identity,{username:'account',token:'synthetic'});
});
test('failed save permits retry; missing auth and invalid nickname make no request',async()=>{
    let fail=true,calls=0,account={username:'a',token:'a'};const states=[];
    const c=createController({identity:()=>account,onState:s=>states.push(s),request:async(_,name)=>{calls++;if(fail)throw Error('offline');return {code:200,data:{nickname:name}};}});
    await c.save('昵称');assert.equal(states.at(-1).status,'error');
    fail=false;await c.save('昵称');assert.equal(states.at(-1).status,'saved');
    account={};await c.save('昵称');assert.equal(states.at(-1).message,'login');
    await c.save('茶'.repeat(31));assert.equal(states.at(-1).message,'invalid');assert.equal(calls,2);
});
test('duplicate save is ignored; account switch or cancellation cannot apply old nickname',async()=>{
    let resolve,account={username:'a',token:'a'},calls=0;const states=[];
    const c=createController({identity:()=>account,onState:s=>states.push(s),request:()=>{calls++;return new Promise(r=>{resolve=r;});}});
    const pending=c.save('甲');await c.save('乙');assert.equal(calls,1);
    account={username:'b',token:'b'};resolve({code:200,data:{nickname:'甲'}});await pending;
    assert.equal(states.at(-1).message,'login');assert.equal(states.some(s=>s.status==='saved'),false);
    const last=c.save('丙');c.cancel();resolve({code:200,data:{nickname:'丙'}});await last;
    assert.equal(states.some(s=>s.status==='saved'),false);
});
test('real editor keeps save separate from contact information and gates unavailable schema',async()=>{
    const node=()=>({value:'',dataset:{},events:{},attrs:{},addEventListener(k,v){this.events[k]=v;},setAttribute(k,v){this.attrs[k]=v;}});
    const nodes=Object.fromEntries(['nickname-editor','pf-nickname','nickname-save','nickname-msg'].map(id=>[id,node()]));
    const labels=['label','hint','save'].map(key=>({dataset:{nicknameText:key}}));nodes['nickname-editor'].querySelectorAll=()=>labels;
    let language='zh';const requests=[];
    const win={document:{getElementById:id=>nodes[id],documentElement:{lang:'zh'},body:{classList:{contains:()=>false}}},
        AuthStorage:{getUser:()=>'account',getToken:()=>'synthetic'},localStorage:{getItem:()=>language},
        MutationObserver:class {observe(){}},addEventListener(){},AbortController,setTimeout:()=>1,clearTimeout(){},
        fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({code:200,data:{nickname:JSON.parse(options.body).nickname}})};}};
    const editor=mount(win);assert.equal(nodes['nickname-save'].disabled,true);
    editor.load(undefined);assert.equal(nodes['nickname-save'].disabled,true);
    editor.load('');assert.equal(nodes['nickname-save'].disabled,false);
    nodes['pf-nickname'].value='茶友';nodes['nickname-save'].events.click();await flush();
    assert.equal(requests[0].options.method,'PATCH');assert.deepEqual(JSON.parse(requests[0].options.body),{nickname:'茶友'});
    assert.equal(nodes['nickname-msg'].textContent,'昵称已保存');assert.equal(nodes['pf-nickname'].value,'茶友');
    assert.equal(nodes['nickname-save'].disabled,false);
    win.AuthStorage.getUser=()=>'other-account';nodes['nickname-save'].events.click();await flush();
    assert.equal(requests.length,1);assert.equal(nodes['nickname-msg'].textContent,'登录已过期，请重新登录');
});
