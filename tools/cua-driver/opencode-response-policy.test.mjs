import test from 'node:test';
import assert from 'node:assert/strict';
import {restrictActionResult} from './opencode-policy.mjs';

test('background fallback advice cannot request foreground or assert no side effect',()=>{
  const result={content:[{type:'text',text:'Sent text. Retry with delivery_mode:"foreground".'}],structuredContent:{effect:'unverifiable',route:'synthetic_events',delivery:{mode:'background'},escalation:{target:'foreground',reason:'delivery_failed'},summary:'Retry foreground'}};
  const actual=restrictActionResult('type_text',result);
  assert.equal(actual.structuredContent.effect,'unverifiable');
  assert.equal(actual.structuredContent.route,'synthetic_events');
  assert.deepEqual(actual.structuredContent.delivery,{mode:'background'});
  assert.equal(actual.structuredContent.escalation,undefined);
  assert.ok(actual.content[0].text.includes('may already have occurred'));
  assert.ok(actual.content[0].text.includes('BACKGROUND_ONLY_UNSUPPORTED'));
  assert.ok(!JSON.stringify(actual).includes('Retry with delivery_mode'));
  assert.equal(result.structuredContent.escalation.target,'foreground');
});

test('normal results, verification errors and read-only responses stay unchanged',()=>{
  for(const name of ['click','type_text','get_window_state']) {
    const value={isError:true,content:[{type:'text',text:'permission denied'}],structuredContent:{code:'permission_denied'}};
    assert.equal(restrictActionResult(name,value),value);
  }
  const read={structuredContent:{escalation:{target:'foreground'}},content:[]};
  assert.equal(restrictActionResult('get_window_state',read),read);
});
