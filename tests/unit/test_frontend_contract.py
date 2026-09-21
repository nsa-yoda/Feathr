"""Docker-free contract checks for the Feature 023 reviewer console."""

from pathlib import Path

ROOT = Path(__file__).parents[2]
INDEX = ROOT / "frontend/public/index.html"
NGINX = ROOT / "frontend/nginx.conf"
VISUALIZER = ROOT / "frontend/public/visualizer.js"


def test_console_has_required_views_and_accessible_navigation() -> None:
    text = INDEX.read_text()
    for view in (
        "dashboard",
        "generator",
        "events",
        "search",
        "analytics",
        "realtime",
        "operations",
    ):
        assert view in text
    assert 'aria-label="Primary navigation"' in text
    assert 'aria-live="polite"' in text
    assert 'role="alert"' in text


def test_console_uses_same_origin_api_and_safe_problem_rendering() -> None:
    text = INDEX.read_text()
    for path in (
        "/health/ready",
        "/health/components",
        "/events",
        "/events/search",
        "/events/stats",
        "/events/stats/realtime",
    ):
        assert f"'{path}" in text or f"`{path}" in text
    assert "fetch(`/api${path}" in text
    assert "request_id" in text
    assert "Raw payloads" in text
    assert "JSON.stringify(item.metadata" in text
    assert "state.last" in text
    assert "eventsView(cursor='')" in text
    assert "query.set('user_id'" in text
    assert "query.set('event_type'" in text
    assert 'id="events-next"' in text
    assert "events/stats/realtime" in text
    assert "events/search/rebuild" in text
    assert "completed_at" in text and "started_at" in text
    assert "content-type" in text
    assert "response.status !== 202" in text


def test_generator_burst_is_bounded_and_problems_are_visible() -> None:
    text = INDEX.read_text()
    assert "MAX_BURST = 500" in text
    assert "BURST_WINDOW_MS = 5000" in text
    assert 'name="burst" type="number" min="1" max="500"' in text
    assert "body.event_id" in text
    assert "body.request_id" in text
    assert "Metadata must be valid JSON" in text
    assert 'role="status"' in text


def test_console_has_behavioral_contract_markers_for_states_and_requests() -> None:
    text = INDEX.read_text()
    assert "Promise.all" in text and "health/ready" in text and "events/stats/realtime" in text
    assert "Refreshing dashboard…" in text
    assert "Refresh failed;" in text
    assert "MAX_BURST = 500" in text and "pacedBurst(count" in text
    assert "response.status" in text and "response.ok" in text
    assert "No canonical events match" in text and "No projected events found yet" in text
    assert "Retry" in text and 'role="alert"' in text


def test_nginx_proxies_api_and_serves_spa_fallback() -> None:
    text = NGINX.read_text()
    assert "location /api/" in text
    assert "proxy_pass http://app:8000/" in text
    assert "try_files $uri $uri/ /index.html" in text


def test_console_exposes_shareable_routes_and_history_navigation() -> None:
    text = INDEX.read_text()
    assert "const routePath = (view) => `/${view}`" in text
    assert "const viewFromPath" in text
    assert 'href="${routePath(v)}"' in text
    assert "pushState" in text and "popstate" in text
    assert "getView:()=>state.view" in text


def test_visualizer_legends_apply_series_colors_over_css_defaults() -> None:
    text = VISUALIZER.read_text()
    assert text.count(".style('fill', (name) => color(name))") == 2
    assert (
        ".viz-chart .legend text { fill:var(--muted)"
        in (ROOT / "frontend/public/visualizer.css").read_text()
    )


def test_browser_free_javascript_harness_exercises_client_helpers(tmp_path) -> None:
    """Execute the client query/burst/escaping helpers without a browser daemon."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("Node is required for the browser-free UI harness")
    script = INDEX.read_text().split("<script>", 1)[1].split("</script>", 1)[0]
    script_path = tmp_path / "console.js"
    script_path.write_text(script)
    harness = tmp_path / "harness.js"
    harness.write_text(
        "const fs=require('fs'),vm=require('vm');"
        "const elements=new Map();"
        "function element(id){if(!elements.has(id)) elements.set(id,{id,innerHTML:'',onclick:null,querySelectorAll:()=>[]});return elements.get(id);}"  # noqa: E501
        "const document={getElementById:element}; let calls=[]; let mode='ok';"  # noqa: E501
        "const json=(body,status=200,type='application/json')=>({ok:status>=200&&status<300,status,headers:{get:(k)=>type},text:async()=>type.includes('json')?JSON.stringify(body):body});"  # noqa: E501
        "const context={window:{location:{pathname:'/operations'},history:{pushState(){},replaceState(){}}},URLSearchParams,console,setTimeout:(fn)=>{fn();return 0;},fetch:async(url,opts)=>{calls.push({url,opts}); if(mode==='pending') return new Promise(()=>{}); if(mode==='fail') return json({status:503,detail:'down',request_id:'r'},503); if(url.includes('/metrics')) return json('# HELP queue\\nqueue 1',200,'text/plain'); if(url.includes('/events/stats/realtime')) return json({total_events:2,by_event_type:{demo:2},generated_at:'now'}); if(url.includes('/health')) return json({status:'healthy',components:{queue:{state:'healthy'}}}); if(url.includes('/events/search/rebuild')) return json({phase:'idle'}); if(opts&&opts.method==='POST') return json({event_id:'e',request_id:'r',status:'queued'},202); return json({items:[],next_cursor:null});}};"  # noqa: E501
        "vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context); context.document=document; const h=context.window.__feathrConsole;"  # noqa: E501
        "(async()=>{if(h.getView()!=='operations'||h.routePath('operations')!=='/operations'||h.viewFromPath('/unknown')!=='dashboard')process.exit(12); if(h.boundedBurst(999)!==500||h.boundedBurst(0)!==1||h.burstOffset(0,500)!==0||h.burstOffset(499,500)!==5000)process.exit(1); const parsed=h.parseMetrics('# HELP x\\nx{outcome=hit} 3\\nx_count 2\\nx_sum 1'); if(h.metricValue(parsed,'x',{outcome:'hit'})!==3||h.metricAverage(parsed,'x')!==0.5)process.exit(11); const q=h.eventQuery({user_id:'u',event_type:'t'},'cursor'); if(!q.includes('user_id=u')||!q.includes('event_type=t')||!q.includes('cursor=cursor'))process.exit(2); if(!h.searchQuery({q:'x',user_id:'u'}).includes('user_id=u'))process.exit(3); if(h.esc('<secret>')!=='&lt;secret&gt;')process.exit(4); await h.generator(); const form=element('generator-form'); context.FormData=class{constructor(){ }get(k){return {event_type:'demo',timestamp:'',user_id:'u',source_url:'https://e.invalid',metadata:'{}',burst:'999'}[k]}}; await form.onsubmit({preventDefault(){},currentTarget:form}); if(calls.filter(c=>c.opts&&c.opts.method==='POST').length!==500||element('generator-submit').disabled)process.exit(7); await h.dashboard(); mode='fail'; await h.dashboard(); if(!element('app').innerHTML.includes('Refresh failed')||!element('dashboard-retry').onclick)process.exit(8); mode='pending'; h.dashboard(); const pendingHtml=element('app').innerHTML; if(!pendingHtml.includes('Refreshing dashboard')||pendingHtml.includes('Refresh failed'))process.exit(9); })().catch(()=>process.exit(10));"  # noqa: E501
    )
    result = subprocess.run(
        [node, str(harness), str(script_path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
