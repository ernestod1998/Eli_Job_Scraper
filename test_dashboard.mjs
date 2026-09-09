import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
import vm from 'node:vm';
const html=readFileSync(new URL('triage.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
function extract(name) {
  const start=script.indexOf(`function ${name}(`);
  assert(start>=0, `${name} exists`);
  const open=script.indexOf('{', start); let depth=0;
  for(let i=open;i<script.length;i++) {
    if(script[i]==='{')depth++;
    if(script[i]==='}' && --depth===0) return script.slice(start,i+1);
  }
  throw Error(`Unbalanced ${name}`);
}
const context={Date};vm.createContext(context);
vm.runInContext(['classifyRole','classifySeniority','decide','normalizeTriage','mergeTriage'].map(extract).join('\n'),context);
assert.equal(context.classifyRole('Senior Financial Analyst'),'Finance/Accounting');
assert.equal(context.classifyRole('Buyer II'),'Purchasing');
assert.equal(context.classifyRole('Budget Analyst'),'Budget/Fiscal');
assert.equal(context.classifyRole('Management Analyst'),'Administrative');
assert.equal(context.classifySeniority('Senior Financial Analyst'),'Senior');
assert.equal(context.mergeTriage({a:{s:'saved',t:2}},{a:{s:'dismissed',t:1}}).a.s,'saved');
assert.equal(context.mergeTriage({a:{s:'saved',t:1}},{a:{s:null,t:2}}).a.s,null);
assert(html.includes("readJson('eliTriage:decisions:v1')"));
assert(!/pjTriage|jackieTriage|https:\/\/job-triage-sync/.test(html));
assert(html.includes("const SYNC_URL = ''"));
assert(html.includes('return !!(SYNC_URL &&'));
assert(html.includes("data.owner !== 'eli'"));
assert(html.includes('data.version === 1'));
assert(html.includes('data.triage = data.decisions'));
assert(html.includes("owner: 'eli'"));
assert(html.includes("j.california_eligibility === 'excluded'"));
assert(html.includes('California eligibility unverified'));
assert(html.includes('Role fit unverified'));
assert(html.includes("name: 'all_jobs.json'"));
assert(!/name: '(?:linkedin|indeed|hollywood)_jobs.json'/.test(html));
assert(html.includes("fetch('source_status.json'"));
for(const id of ['kpi-total','chart-companies','chart-roles','chart-salary','sal-min','filter-source','filter-role','filter-sen','filter-date','filter-sort','filter-state','view-map','export-btn','import-btn'])assert(html.includes(`id="${id}"`));
console.log('Original dashboard controls, Eli classifications, decisions migration and isolation passed');
