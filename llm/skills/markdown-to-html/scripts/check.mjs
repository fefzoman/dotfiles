import { spawn } from 'node:child_process';
import { readFile, readdir, writeFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { mkdtemp, stat } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

if (process.argv.includes('--help')) {
  console.log('Usage: node check.mjs HTML_DIRECTORY\nOptional: CHROME_BIN=/path/to/chromium');
  process.exit(0);
}
assert.equal(typeof WebSocket, 'function', 'Use an installed Node version with built-in WebSocket');
const root = resolve(process.argv[2] || process.cwd());
const pages = (await readdir(root)).filter(name => name.endsWith('.html')).sort();
assert(pages.length, 'No HTML pages found');
const artifacts = await mkdtemp(join(tmpdir(), 'markdown-html-check-'));
console.log(`Browser artifacts: ${artifacts}`);
const browserPath = process.env.CHROME_BIN || (process.platform === 'darwin' ? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' : 'chromium');
const chrome = spawn(browserPath, [
  '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
  '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
  `--user-data-dir=${join(artifacts, 'browser')}`, '--allow-file-access-from-files', 'about:blank'
], { stdio: ['ignore', 'ignore', 'pipe'] });
let browserLog = '';
let startupError;
chrome.on('error', error => { startupError = error; });
chrome.stderr.on('data', chunk => { browserLog += chunk.toString(); });
const pause = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
let socket;
let command;
try {
  for (let attempt = 0; attempt < 100 && !browserLog.includes('DevTools listening on'); attempt++) {
    assert(!startupError, `Could not start browser: ${startupError?.message}`);
    assert.equal(chrome.exitCode, null, 'Chrome exited before startup');
    await pause(100);
  }
  const endpoint = browserLog.match(/DevTools listening on (ws:\/\/\S+)/)?.[1];
  assert(endpoint, 'Chrome did not expose its test connection');
  socket = new WebSocket(endpoint);
  await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
  const pending = new Map();
  let nextId = 0;
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    const job = pending.get(message.id);
    if (!job) return;
    pending.delete(message.id);
    message.error ? job.reject(new Error(JSON.stringify(message.error))) : job.resolve(message.result);
  };
  command = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await command('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await command('Target.attachToTarget', { targetId, flatten: true });
  const send = (method, params) => command(method, params, sessionId);
  await send('Page.enable');
  await send('Page.addScriptToEvaluateOnNewDocument', { source: 'window.__lessonErrors=[]; window.addEventListener("error",event=>window.__lessonErrors.push(event.message));' });
  const check = `(() => {
    const tests=[];
    const check=(name,condition)=>tests.push({name,pass:Boolean(condition)});
    check('No JavaScript errors',window.__lessonErrors.length===0);
    check('Enhanced controls initialized',document.documentElement.classList.contains('enhanced'));
    check('No walkthrough controls',!document.querySelector('.walkthrough,.walkthrough-controls,[data-step],#next-step'));
    check('Explanations initially visible',![...document.querySelectorAll('main li,main tbody > tr')].some(item=>item.hidden));
    check('Shared CSS loaded',getComputedStyle(document.body).backgroundColor==='rgb(247, 245, 239)');
    const headingStyle=getComputedStyle(document.querySelector('main h1'));
    check('Reference heading typography',headingStyle.fontFamily.includes('ui-serif') && headingStyle.fontWeight==='500' && parseFloat(headingStyle.fontSize)<=62);
    check('Reference reading typography',getComputedStyle(document.body).fontFamily.includes('system-ui') && parseFloat(getComputedStyle(document.body).lineHeight)>=25);
    const diagrams=[...document.querySelectorAll('figure.lesson-diagram')];
    check('HTML diagrams have accessible captions',diagrams.every(figure=>figure.querySelector('figcaption[id]')?.id===figure.getAttribute('aria-labelledby')));
    check('HTML diagram explanations stay unfiltered',diagrams.every(figure=>!figure.querySelector('.table-filter,[hidden]')));
    check('HTML diagrams contain selectable content',diagrams.every(figure=>figure.querySelector('.diagram-card,.diagram-tree,table,svg.vector-diagram') && !figure.querySelector('img,object,iframe')));
    check('HTML diagram cards fit their frame',diagrams.every(figure=>[...figure.querySelectorAll('.diagram-card')].every(card=>card.scrollWidth<=card.clientWidth+1 && card.getBoundingClientRect().right<=figure.getBoundingClientRect().right)));
    const vectors=[...document.querySelectorAll('svg.vector-diagram')];
    check('Vector diagrams have accessible descriptions',vectors.every(svg=>svg.getAttribute('role')==='img' && svg.getAttribute('aria-labelledby')?.split(' ').every(id=>svg.querySelector('[id="'+id+'"]')?.textContent.trim())));
    check('Vector labels fit the drawing',vectors.every(svg=>{const view=svg.viewBox.baseVal;return [...svg.querySelectorAll('text')].every(text=>{const box=text.getBBox();return box.x>=view.x-1 && box.y>=view.y-1 && box.x+box.width<=view.x+view.width+1 && box.y+box.height<=view.y+view.height+1;});}));
    check('Vector diagrams stay in local scroll containers',vectors.every(svg=>svg.parentElement.classList.contains('vector-scroll') && getComputedStyle(svg.parentElement).overflowX==='auto'));
    check('All images loaded',[...document.images].every(image=>image.complete && image.naturalWidth>0));
    check('Images have alt text',[...document.images].every(image=>image.hasAttribute('alt') && image.alt.trim().length>0));
    check('Images capped at 675px',[...document.images].every(image=>image.getBoundingClientRect().width<=675));
    check('No page overflow',document.documentElement.scrollWidth<=innerWidth);
    const toggle=document.querySelector('#menu-toggle'), menu=document.querySelector('#lesson-menu');
    toggle.click();
    check('Menu collapses',menu.hidden && toggle.getAttribute('aria-expanded')==='false' && toggle.getAttribute('aria-label')==='Show contents');
    check('Reopen control remains visible',toggle.getBoundingClientRect().width===44 && getComputedStyle(toggle).display!=='none' && !menu.contains(toggle));
    check('Hidden menu removes links from layout',getComputedStyle(menu).display==='none');
    check('Collapsed layout fits',document.documentElement.scrollWidth<=innerWidth);
    if(innerWidth>760) check('Collapsed rail is 44px',getComputedStyle(document.querySelector('.layout')).gridTemplateColumns.split(' ')[0]==='44px');
    toggle.click();
    check('Menu reopens',!menu.hidden && toggle.getAttribute('aria-expanded')==='true');
    const search=document.querySelector('.table-filter input');
    if(search){
      const rows=[...search.closest('.table-filter').nextElementSibling.querySelectorAll('tbody > tr')];
      const change=value=>{ search.value=value; search.dispatchEvent(new Event('input',{bubbles:true})); };
      change('__no_such_linux_reference_row__');
      check('Table empty result',rows.every(row=>row.hidden));
      change(rows[0].cells[0].textContent.trim().split(/\\s+/)[0]);
      check('Table matching result',!rows[0].hidden);
      change('');
      check('Table clear restores rows',rows.every(row=>!row.hidden));
    }
    const disclosure=document.querySelector('details');
    if(disclosure){disclosure.querySelector('summary').click();check('Answer disclosure opens',disclosure.open);disclosure.querySelector('summary').click();}
    const checkbox=document.querySelector('input[type="checkbox"]');
    if(checkbox){checkbox.click();check('Checklist toggles',checkbox.checked);checkbox.click();}
    const role=document.querySelector('[data-role="other"]');
    if(role){role.click();check('Overview permission control retained',document.querySelector('[data-bits="other"]').classList.contains('selected'));document.querySelector('[data-role="owner"]').click();}
    const theme=document.querySelector('#theme-toggle');
    const switchRect=theme.getBoundingClientRect();
    check('Theme switch at top right',switchRect.left>innerWidth/2 && switchRect.right<=innerWidth && switchRect.top<120 && switchRect.height===44);
    const edition=document.querySelector('.edition').getBoundingClientRect();
    check('Theme switch does not overlap heading',switchRect.left>=edition.right || switchRect.top>=edition.bottom || switchRect.bottom<=edition.top);
    theme.click();
    check('Dark palette applied',document.documentElement.dataset.theme==='dark' && getComputedStyle(document.body).backgroundColor==='rgb(21, 28, 32)' && getComputedStyle(document.documentElement).colorScheme==='dark');
    check('Theme accessible state',theme.getAttribute('aria-pressed')==='true' && theme.getAttribute('aria-label')==='Switch to light mode');
    check('Theme saved',localStorage.getItem('linux-theme')==='dark');
    check('Theme survives reload URL',new URL(location.href).searchParams.get('theme')==='dark');
    check('Theme follows lesson links',[...document.querySelectorAll('.footer a')].filter(link=>new URL(link.href).pathname.endsWith('.html') && !link.getAttribute('href').startsWith('#')).every(link=>new URL(link.href).searchParams.get('theme')==='dark'));
    check('Dark layout fits',document.documentElement.scrollWidth<=innerWidth);
    const vars=getComputedStyle(document.documentElement);
    function luminance(hex){const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(c=>c<=.04045?c/12.92:((c+.055)/1.055)**2.4);return rgb.reduce((sum,c,i)=>sum+c*[.2126,.7152,.0722][i],0);}
    function contrast(a,b){const levels=[luminance(vars.getPropertyValue(a).trim()),luminance(vars.getPropertyValue(b).trim())].sort((a,b)=>a-b);return (levels[1]+.05)/(levels[0]+.05);}
    check('Body contrast above 7:1',contrast('--ink','--paper')>=7);
    check('Muted contrast above 4.5:1',contrast('--muted','--card')>=4.5);
    check('Accent contrast above 4.5:1',contrast('--green','--mint')>=4.5);
    check('Active button contrast above 4.5:1',contrast('--on-accent','--green')>=4.5);
    theme.click();
    check('Light palette restored',document.documentElement.dataset.theme==='light' && getComputedStyle(document.body).backgroundColor==='rgb(247, 245, 239)' && theme.getAttribute('aria-pressed')==='false');
    theme.click();
    const chapter=document.querySelector('.chapter');
    chapter.scrollIntoView();
    return {width:innerWidth,tests,errors:window.__lessonErrors,ids:[...document.querySelectorAll('[id]')].map(element=>element.id),refs:[...document.querySelectorAll('a[href],link[href],script[src],img[src]')].map(element=>new URL(element.getAttribute('href')||element.getAttribute('src'),document.baseURI).href)};
  })()`;
  let total = 0;
  for (const viewport of [{ width: 1440, height: 1100, mobile: false }, { width: 390, height: 844, mobile: true }]) {
    await send('Emulation.setDeviceMetricsOverride', { ...viewport, deviceScaleFactor: 1 });
    for (const page of pages) {
      const target = pathToFileURL(join(root,page));
      target.searchParams.set('theme','light');
      const url = target.href;
      await send('Page.navigate', { url });
      const ready = await send('Runtime.evaluate', { expression: `(async()=>{for(let i=0;i<150;i++){if(location.href===${JSON.stringify(url)} && document.readyState==='complete')return true;await new Promise(r=>setTimeout(r,50));}return false})()`, awaitPromise: true, returnByValue: true });
      assert.equal(ready.result.value, true, `${page}: load timed out`);
      const evaluated = await send('Runtime.evaluate', { expression: check, returnByValue: true });
      assert(!evaluated.exceptionDetails, `${page}: test exception ${JSON.stringify(evaluated.exceptionDetails)}`);
      const report = evaluated.result.value;
      report.tests.push({name:'Requested viewport width',pass:report.width===viewport.width});
      const reflected = await send('Runtime.evaluate', {expression:`[...document.querySelectorAll('[data-token]')].every(element=>element.textContent.trim()===getComputedStyle(document.documentElement).getPropertyValue(element.dataset.token).trim())`,returnByValue:true});
      report.tests.push({name:'Design reference tokens match active theme',pass:reflected.result.value===true});
      assert.equal(report.ids.length,new Set(report.ids).size,`${page}: duplicate DOM IDs`);
      for(const ref of report.refs){
        const url=new URL(ref);
        if(url.protocol!=='file:') continue;
        const target=fileURLToPath(url);
        assert((await stat(target)).isFile(),`${page}: missing local file ${target}`);
        if(url.hash && target.endsWith('.html')){
          const targetHtml=await readFile(target,'utf8');
          const ids=[...targetHtml.matchAll(/\bid=["']([^"']+)["']/g)].map(match=>match[1]);
          assert(ids.includes(decodeURIComponent(url.hash.slice(1))),`${page}: missing anchor ${ref}`);
        }
      }
      const failed = report.tests.filter(test => !test.pass);
      if (failed.length) {
        const layout = await send('Runtime.evaluate', {expression:`JSON.stringify({viewport:innerWidth,client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll('main *')].filter(element=>{const rect=element.getBoundingClientRect();return rect.right>document.documentElement.clientWidth+1 && rect.width>0 && getComputedStyle(element).position!=='absolute'}).slice(0,12).map(element=>({tag:element.tagName,class:element.className,text:element.textContent.slice(0,120),width:element.getBoundingClientRect().width}))})`,returnByValue:true});
        console.log(`Layout diagnostics: ${layout.result.value}`);
      }
      total += report.tests.length;
      console.log(`${page} @ ${report.width}px: ${report.tests.length} checks, ${failed.length} failures`);
      assert.deepEqual(failed, [], `${page}: ${JSON.stringify(failed)}; errors: ${JSON.stringify(report.errors)}`);
      if ((viewport.width === 1440 && [pages[0],pages.at(-1)].includes(page)) || (viewport.width === 390 && page === pages.at(-1))) {
        await send('Runtime.evaluate', { expression: 'window.scrollTo(0,0)' });
        const screenshot = await send('Page.captureScreenshot', { format: 'png' });
        await writeFile(join(artifacts,`${page.replace('.html','')}-${viewport.width}.png`), Buffer.from(screenshot.data,'base64'));
      }
    }
  }
  await send('Page.navigate', { url: pathToFileURL(join(root,pages[0])).href+'?theme=dark' });
  await pause(300);
  const persisted = await send('Runtime.evaluate', { expression: `document.documentElement.dataset.theme==='dark' && document.querySelector('#theme-toggle').getAttribute('aria-pressed')==='true'`, returnByValue:true });
  assert.equal(persisted.result.value,true,'Saved theme applied on navigation');
  await send('Page.reload');
  await pause(300);
  const reloaded = await send('Runtime.evaluate', { expression: `document.documentElement.dataset.theme==='dark'`,returnByValue:true });
  assert.equal(reloaded.result.value,true,'Dark theme survives reload');
  await send('Page.addScriptToEvaluateOnNewDocument', {source:'Object.defineProperty(window,"localStorage",{get(){throw new DOMException("Storage unavailable","SecurityError");}});'});
  await send('Page.navigate', {url:pathToFileURL(join(root,pages.at(-1))).href+'?theme=dark'});
  await pause(300);
  const blockedStorage = await send('Runtime.evaluate', {expression:`(()=>{const dark=document.documentElement.dataset.theme==='dark';document.querySelector('#theme-toggle').click();return dark && document.documentElement.dataset.theme==='light' && document.documentElement.classList.contains('enhanced') && window.__lessonErrors.length===0})()`,returnByValue:true});
  assert.equal(blockedStorage.result.value,true,'Theme works with storage blocked');
  await send('Emulation.setScriptExecutionDisabled', { value: true });
  await send('Page.navigate', { url: pathToFileURL(join(root,pages[0])).href });
  await pause(300);
  const fallback = await send('Runtime.evaluate', { expression: `document.querySelector('main').textContent.trim().length>0 && !document.querySelector('main [hidden]') && getComputedStyle(document.querySelector('#menu-toggle')).display==='none'`, returnByValue: true });
  assert.equal(fallback.result.value,true,'No-JavaScript reading fallback');
  console.log(`PASS: ${total} browser checks across ${pages.length} pages at desktop and 390px phone widths; no-JavaScript fallback also passed.`);
} finally {
  await writeFile(join(artifacts,'browser.log'), browserLog);
  if (command && socket?.readyState === WebSocket.OPEN) {
    await command('Browser.close').catch(() => {});
    socket.close();
  } else if (chrome.exitCode === null) {
    chrome.kill('SIGTERM');
  }
}
