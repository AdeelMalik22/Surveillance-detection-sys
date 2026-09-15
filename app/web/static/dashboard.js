const feeds = [];
const classes = ['total', 'person', 'car', 'motorcycle', 'bus', 'truck'];
const $ = id => document.getElementById(id);

function summary() {
    $('feed-count').textContent = `${feeds.length} feed${feeds.length === 1 ? '' : 's'}`;
    $('active-cameras').textContent = feeds.filter(f => f.live).length;
    $('summary-people').textContent = feeds.reduce((n, f) => n + (f.people || 0), 0);
    $('summary-vehicles').textContent = feeds.reduce((n, f) => n + (f.vehicles || 0), 0)
}

function addCard(feed, index) {
    const card = document.createElement('article');
    card.className = 'card';
    card.innerHTML = `<div class="card-head"><strong>Camera ${index + 1}</strong><span class="status">READY</span></div><div class="screen"><span class="empty">Start detection to view feed</span><img style="display:none"></div><div class="actions"><button class="action start">Start detection</button><button class="action stop" disabled>Stop</button></div><div class="counters">${classes.map(c => `<div class="counter"><small>${c}</small><b data-c="${c}">0</b></div>`).join('')}</div><div class="card-foot">${feed.filename}</div>`;
    const image = card.querySelector('img'), empty = card.querySelector('.empty'),
        status = card.querySelector('.status'), start = card.querySelector('.start'),
        stop = card.querySelector('.stop');
    let timer;

    async function refresh() {
        const response = await fetch(`/api/counts/${feed.session_id}`);
        if (!response.ok) return;
        const data = await response.json();
        classes.forEach(c => card.querySelector(`[data-c="${c}"]`).textContent = data[c] || 0);
        feed.people = data.person || 0;
        feed.vehicles = (data.car || 0) + (data.motorcycle || 0) + (data.bus || 0) + (data.truck || 0);
        summary()
    }

    start.onclick = async () => {
        await fetch(`/api/reset/${feed.session_id}`, {method: 'POST'});
        image.src = `${feed.stream_url}?run=${Date.now()}`;
        image.style.display = 'block';
        empty.style.display = 'none';
        start.textContent = 'Restart';
        stop.disabled = false;
        status.textContent = 'LIVE';
        status.classList.add('live');
        feed.live = true;
        clearInterval(timer);
        timer = setInterval(refresh, 500);
        summary()
    };
    stop.onclick = () => {
        image.removeAttribute('src');
        image.style.display = 'none';
        empty.style.display = 'block';
        stop.disabled = true;
        status.textContent = 'STOPPED';
        status.classList.remove('live');
        feed.live = false;
        clearInterval(timer);
        summary()
    };
    $('camera-grid').appendChild(card)
}

$('upload-form').onsubmit = async event => {
    event.preventDefault();
    const selected = [...$('video-files').files].slice(0, 2 - feeds.length);
    if (!selected.length) return;
    $('upload-button').disabled = true;
    $('notice').textContent = 'Uploading camera feeds…';
    try {
        for (const file of selected) {
            const body = new FormData();
            body.append('file', file);
            const response = await fetch('/api/uploads', {method: 'POST', body}), data = await response.json();
            if (!response.ok) throw Error(data.detail || 'Upload failed');
            feeds.push({...data, filename: file.name, live: false, people: 0, vehicles: 0});
            addCard(feeds.at(-1), feeds.length - 1)
        }
        $('notice').textContent = 'Feeds ready. Start each camera independently.';
        $('video-files').value = '';
        summary()
    } catch (error) {
        $('notice').textContent = error.message
    } finally {
        $('upload-button').disabled = false
    }
};
$('zone-form').onsubmit = async event => {
    event.preventDefault();
    try {
        const response = await fetch('/zones', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                camera_id: $('zone-camera').value,
                zone: {id: $('zone-name').value, polygon: JSON.parse($('zone-polygon').value)}
            })
        });
        const data = await response.json();
        if (!response.ok) throw Error(data.detail || 'Unable to save zone');
        $('zone-message').textContent = 'Zone saved.';
        $('zone-form').reset()
    } catch (error) {
        $('zone-message').textContent = error.message
    }
};

async function loadEvents() {
    const response = await fetch('/events?limit=50');
    const data = await response.json();
    $('event-list').innerHTML = data.length ? data.map(e => `<div class="event"><b>${e.object_class}</b><span>${String(e.camera_id).slice(0, 12)} · ${e.zone_id}</span><small>${new Date(e.timestamp).toLocaleString()} · ${(e.confidence * 100).toFixed(0)}% confidence</small></div>`).join('') : '<p>No events found.</p>'
}

$('refresh-events').onclick = loadEvents;
loadEvents();
summary();
