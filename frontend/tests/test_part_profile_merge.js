import {test} from 'node:test';
import assert from 'node:assert/strict';
import {merge, undoFill} from '../src/lib/part-profile-merge.ts';
const fact = (id, field, value) => ({id, field, value, verification_status: 'unverified'});
test('fills empty scalar and adds multiple aliases without false conflicts', () => {
  const result = merge([], [], [fact('1','name','Lamp'),fact('2','aliases','Farolim'),fact('3','aliases','Feu arrière')], ['aliases']);
  assert.equal(result.facts.length, 3); assert.equal(result.pending.length, 0);
});
test('preserves values typed while AI runs, including newly filled blanks', () => {
  const current = [fact('a','name','My lamp'),fact('b','references','001')];
  const result = merge(current, [], [fact('1','name','Another lamp'),fact('2','references','002')], ['references']);
  assert.deepEqual(result.facts, current); assert.equal(result.pending.length, 2);
});
test('does not overwrite existing scalar or add exact duplicate', () => {
  const original = [fact('a','name','Lamp')];
  const result = merge(original, original, [fact('1','name','Other'),fact('2','name','lamp')], []);
  assert.deepEqual(result.facts, original); assert.equal(result.pending.length, 1);
});
test('recovery does not apply already reviewed or dismissed suggestions again', () => {
  assert.equal(merge([], [], [fact('1','name','Lamp')], [], ['1']).facts.length, 0);
});
test('undo preserves subsequent edits and explicit confirmations', () => {
  const facts = [fact('1','name','Edited'), {...fact('2','references','001'), verification_status:'user_confirmed'}, fact('3','aliases','Farolim')];
  const result = undoFill(facts, [{id:'1',value:'Lamp'},{id:'2',value:'001'},{id:'3',value:'Farolim'}]);
  assert.deepEqual(result.map(f=>f.id), ['1','2']);
});
test('undo restores the user value replaced after explicit review', () => {
  const old = fact('old','name','User lamp');
  const result = undoFill([fact('new','name','AI lamp')], [{id:'new',value:'AI lamp',previous:[old]}]);
  assert.deepEqual(result, [old]);
});
