const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../static/js/buyer-support.js'), 'utf8');
const template = fs.readFileSync(require.resolve('../templates/buyer_support.html'), 'utf8');
const fields = source.slice(source.indexOf('    var preferenceFields ='), source.indexOf('    var labels ='));
const actions = source.slice(source.indexOf('    function fillPreferences('), source.indexOf("    preferenceForm.addEventListener('submit'"));

function setup(reply, failure) {
    const elements = {}, calls = [], buttons = [{disabled: false}];
    const context = { document: { getElementById(id) {
        assert(template.includes('id="' + id + '"'), 'preference field must exist in the actual template');
        return elements[id] || (elements[id] = {value: ''});
    }}, preferenceForm: {querySelectorAll: () => buttons}, preferenceStatus: {textContent: ''},
    api: async (path, method, values) => {
        calls.push(JSON.parse(JSON.stringify({path, method, values})));
        if (failure) throw new Error('更新失败，请重试');
        return {preferences: reply};
    }};
    vm.createContext(context); vm.runInContext(fields + actions, context);
    return {context, calls, buttons, elements};
}

test('six positive and negative preference fields round-trip without hard filters', async () => {
    const values = {categories: ['红茶'], brands: ['甲'], keywords: ['清淡'],
        disliked_categories: ['黑茶'], disliked_brands: ['乙'], disliked_keywords: ['烟香']};
    const x = setup(values); x.context.fillPreferences(values);
    await x.context.updatePreferences('PUT');
    assert.deepEqual(x.calls, [{path: 'preferences/', method: 'PUT', values}]);
    assert.equal(x.buttons[0].disabled, false);
    assert.equal(x.elements['bs-pref-disliked-keywords'].value, '烟香');
});

test('clear sends DELETE without cached values and clears both kinds of fields', async () => {
    const x = setup({categories: [], brands: [], keywords: []});
    x.context.fillPreferences({disliked_categories: ['红茶']});
    await x.context.updatePreferences('DELETE');
    assert.deepEqual(x.calls, [{path: 'preferences/', method: 'DELETE'}]);
    assert.equal(x.elements['bs-pref-disliked-categories'].value, '');
});

test('failed updates retain the editable fields and do not show a success message', async () => {
    const x = setup({}, true); x.context.fillPreferences({disliked_brands: ['甲']});
    await x.context.updatePreferences('PUT');
    assert.equal(x.elements['bs-pref-disliked-brands'].value, '甲');
    assert.equal(x.context.preferenceStatus.textContent, '更新失败，请重试');
    assert.equal(x.buttons[0].disabled, false);
});
