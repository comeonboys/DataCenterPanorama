const BASE = '';
const charts = {};
let metricsMeta = [];

function initChart(id) {
    const dom = document.getElementById(id);
    if (!dom) return null;
    charts[id] = echarts.init(dom, 'dark', { renderer: 'canvas' });
    return charts[id];
}

async function getJSON(url) {
    const res = await fetch(url);
    return res.json();
}

function fmtNumber(n) {
    if (n === undefined || n === null) return '--';
    return Number(n).toFixed(n % 1 === 0 ? 0 : 2);
}

function renderSummary(data) {
    document.getElementById('kpi-hosts').textContent = data.total_hosts;
    document.getElementById('kpi-records').textContent = data.total_records.toLocaleString();
    document.getElementById('kpi-alerts').textContent = data.alerts;
    document.getElementById('kpi-healthy').textContent = data.healthy_hosts;
    document.getElementById('latest-time').textContent = `性能：${data.latest_pref_ts || '--'} | 磁盘：${data.latest_disk_ts || '--'}`;
}

function renderHostTable(rows) {
    const tbody = document.querySelector('#host-table tbody');
    tbody.innerHTML = rows.map(r => {
        const cpuClass = r.cpu_usage > 80 ? 'warn' : 'ok';
        const memClass = r.mem_pct > 85 ? 'warn' : 'ok';
        const diskClass = r.disk_max_util > 90 ? 'warn' : 'ok';
        const loadClass = r.load1 > 5 ? 'warn' : 'ok';
        return `<tr>
            <td>${r.hostid}<br><small>${r.hostname}</small></td>
            <td>${r.model}</td>
            <td>${r.location1} ${r.location2}</td>
            <td>${r.owner}</td>
            <td class="${cpuClass}">${fmtNumber(r.cpu_usage)}</td>
            <td class="${memClass}">${fmtNumber(r.mem_pct)}</td>
            <td class="${loadClass}">${fmtNumber(r.load1)}</td>
            <td class="${diskClass}">${fmtNumber(r.disk_max_util)}</td>
        </tr>`;
    }).join('');
}

function renderTrend(data) {
    const chart = charts['chart-trend'];
    const x = data.map(d => d.hour);
    const y = data.map(d => d.avg_value);
    const metricName = document.querySelector('#trend-metric option:checked')?.text || '指标';
    chart.setOption({
        tooltip: { trigger: 'axis' },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', data: x, axisLabel: { rotate: 30, fontSize: 11 } },
        yAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [{
            name: metricName,
            type: 'line',
            smooth: true,
            symbol: 'none',
            data: y,
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(56,189,248,0.4)' },
                    { offset: 1, color: 'rgba(56,189,248,0.02)' }
                ])
            },
            lineStyle: { width: 2, color: '#38bdf8' }
        }]
    }, true);
}

function renderPie(id, title, data) {
    const chart = charts[id];
    chart.setOption({
        tooltip: { trigger: 'item' },
        legend: { top: '5%', left: 'center', textStyle: { fontSize: 11 } },
        series: [{
            name: title,
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['50%', '60%'],
            itemStyle: { borderRadius: 5, borderColor: '#0f172a', borderWidth: 2 },
            label: { show: false },
            data: data
        }]
    }, true);
}

function renderRank(data) {
    const chart = charts['chart-rank'];
    const hosts = data.map(d => d.hostid);
    const vals = data.map(d => +d.value);
    const metricName = document.querySelector('#rank-metric option:checked')?.text || '指标';
    chart.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
        grid: { left: '3%', right: '8%', bottom: '3%', containLabel: true },
        xAxis: { type: 'value', splitLine: { lineStyle: { color: '#1e293b' } } },
        yAxis: { type: 'category', data: hosts.reverse(), axisLabel: { fontSize: 11 } },
        series: [{
            name: metricName,
            type: 'bar',
            data: vals.reverse(),
            itemStyle: {
                color: new echarts.graphic.LinearGradient(1, 0, 0, 0, [
                    { offset: 0, color: '#818cf8' },
                    { offset: 1, color: '#38bdf8' }
                ]),
                borderRadius: [0, 4, 4, 0]
            }
        }]
    }, true);
}

function renderDiskHeatmap(resp) {
    const chart = charts['chart-disk-heatmap'];
    chart.setOption({
        tooltip: { position: 'top' },
        grid: { left: '12%', right: '8%', top: '8%', bottom: '15%' },
        xAxis: { type: 'category', data: resp.disks, splitArea: { show: true } },
        yAxis: { type: 'category', data: resp.hosts, splitArea: { show: true }, axisLabel: { fontSize: 10 } },
        visualMap: {
            min: 0, max: 100,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: '0%',
            inRange: { color: ['#0f172a', '#38bdf8', '#facc15', '#ef4444'] },
            text: ['高', '低']
        },
        series: [{
            name: '磁盘使用率(%)',
            type: 'heatmap',
            data: resp.data,
            label: { show: true, fontSize: 10, formatter: p => p.data[2] },
            itemStyle: { borderColor: '#0f172a', borderWidth: 1 }
        }]
    }, true);
}

function renderNetwork(data) {
    const chart = charts['chart-network'];
    const x = data.map(d => d.hour);
    chart.setOption({
        tooltip: { trigger: 'axis' },
        legend: { data: ['入站', '出站'], top: 0 },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: x, axisLabel: { rotate: 30, fontSize: 10 } },
        yAxis: { type: 'value', name: 'MB/s', splitLine: { lineStyle: { color: '#1e293b' } } },
        series: [
            {
                name: '入站', type: 'line', smooth: true, symbol: 'none',
                data: data.map(d => d.net_in),
                areaStyle: { opacity: 0.2 }, lineStyle: { color: '#34d399' }, itemStyle: { color: '#34d399' }
            },
            {
                name: '出站', type: 'line', smooth: true, symbol: 'none',
                data: data.map(d => d.net_out),
                areaStyle: { opacity: 0.2 }, lineStyle: { color: '#f472b6' }, itemStyle: { color: '#f472b6' }
            }
        ]
    }, true);
}

function renderAlerts(rows) {
    const tbody = document.querySelector('#alert-table tbody');
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#64748b">当前无告警</td></tr>';
        return;
    }
    tbody.innerHTML = rows.map(r => `<tr>
        <td>${r.hostid}<br><small>${r.hostname}</small></td>
        <td>${r.model}</td>
        <td>${r.location1}</td>
        <td class="${r.cpu_usage > 80 ? 'warn' : ''}">${fmtNumber(r.cpu_usage)}</td>
        <td class="${r.mem_pct > 85 ? 'warn' : ''}">${fmtNumber(r.mem_pct)}</td>
        <td class="${r.load1 > 5 ? 'warn' : ''}">${fmtNumber(r.load1)}</td>
        <td class="${r.disk_max_util > 90 ? 'warn' : ''}">${fmtNumber(r.disk_max_util)}</td>
    </tr>`).join('');
}

function populateMetricsSelect() {
    const trendSel = document.getElementById('trend-metric');
    const rankSel = document.getElementById('rank-metric');
    const options = metricsMeta.map(m => `<option value="${m.mod}" ${m.mod === 'cpu_usage' ? 'selected' : ''}>${m.desc} (${m.unit})</option>`).join('');
    trendSel.innerHTML = options;
    rankSel.innerHTML = options + '<option value="disk_max_util">磁盘最大使用率 (%)</option>';
}

async function loadSummary() { renderSummary(await getJSON('/api/summary')); }
async function loadHostStatus() { renderHostTable(await getJSON('/api/host_status')); }
async function loadTrend() {
    const metric = document.getElementById('trend-metric').value;
    const hours = document.getElementById('trend-hours').value;
    const data = await getJSON(`/api/trends?metric=${metric}&hours=${hours}`);
    renderTrend(data);
}
async function loadDistribution() {
    renderPie('chart-model', '机型分布', await getJSON('/api/distribution?field=model'));
    renderPie('chart-location', '机房分布', await getJSON('/api/distribution?field=location1'));
}
async function loadRank() {
    const metric = document.getElementById('rank-metric').value;
    const data = await getJSON(`/api/rank?metric=${metric}&limit=10`);
    renderRank(data);
}
async function loadDiskHeatmap() { renderDiskHeatmap(await getJSON('/api/disk_heatmap')); }
async function loadNetwork() { renderNetwork(await getJSON('/api/network_io')); }
async function loadAlerts() { renderAlerts(await getJSON('/api/alerts')); }

async function init() {
    ['chart-trend', 'chart-model', 'chart-location', 'chart-rank', 'chart-disk-heatmap', 'chart-network'].forEach(initChart);
    window.addEventListener('resize', () => Object.values(charts).forEach(c => c.resize()));

    metricsMeta = await getJSON('/api/metrics_meta');
    populateMetricsSelect();

    document.getElementById('trend-metric').addEventListener('change', loadTrend);
    document.getElementById('trend-hours').addEventListener('change', loadTrend);
    document.getElementById('rank-metric').addEventListener('change', loadRank);
    document.getElementById('refresh-btn').addEventListener('click', refreshAll);

    await refreshAll();
    setInterval(refreshAll, 30000);
}

async function refreshAll() {
    await Promise.all([
        loadSummary(),
        loadHostStatus(),
        loadTrend(),
        loadDistribution(),
        loadRank(),
        loadDiskHeatmap(),
        loadNetwork(),
        loadAlerts()
    ]);
}

document.addEventListener('DOMContentLoaded', init);
