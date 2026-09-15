import { renderSidebar } from './components/sidebar.js';
import { renderEvents } from './components/event-table.js';
import { openZoneModal } from './components/zone-modal.js';

const feeds = [];
const classes = ['total', 'person', 'car', 'motorcycle', 'bus', 'truck'];
const eventPageSize = 10;
const $ = (id) => document.getElementById(id);

function updateSummary() {
  let activeCameras = 0;
  let people = 0;
  let vehicles = 0;

  feeds.forEach((feed) => {
    activeCameras += feed.live ? 1 : 0;
    people += feed.people || 0;
    vehicles += feed.vehicles || 0;
  });

  $('active').textContent = activeCameras;
  $('people').textContent = people;
  $('vehicles').textContent = vehicles;
  $('events-count').textContent = (window.eventData || []).length;
}

function setActiveView(viewName) {
  document.querySelectorAll('[data-view]').forEach((view) => {
    view.classList.toggle('active', view.dataset.view === viewName);
  });
  document.querySelectorAll('.side-link').forEach((link) => {
    link.classList.toggle('active', link.dataset.target === viewName);
  });
}

function addCard(feed, index) {
  const root = document.createElement('article');
  root.className = 'camera-card';
  root.innerHTML = `
    <header>
      <div>
        <small>CAMERA ${index + 1}</small>
        <h3>${feed.filename}</h3>
      </div>
      <span class="badge">READY</span>
    </header>
    <div class="feed">
      <span class="empty">Start detection to view this feed</span>
      <img style="display:none" alt="${feed.filename} detection stream">
    </div>
    <div class="actions">
      <button class="primary start" type="button">Start</button>
      <button class="ghost stop" type="button" disabled>Stop</button>
      <button class="ghost zone" type="button">Zone</button>
    </div>
    <div class="counter-row">
      ${classes.map((name) => `<div><small>${name}</small><b data-c="${name}">0</b></div>`).join('')}
    </div>
  `;

  const img = root.querySelector('img');
  const empty = root.querySelector('.empty');
  const badge = root.querySelector('.badge');
  const start = root.querySelector('.start');
  const stop = root.querySelector('.stop');
  let timer;

  async function refreshCounts() {
    const counts = await fetch(`/api/counts/${feed.session_id}`).then((response) => response.json());
    classes.forEach((name) => {
      root.querySelector(`[data-c="${name}"]`).textContent = counts[name] || 0;
    });
    feed.people = counts.person || 0;
    feed.vehicles = (counts.car || 0) + (counts.motorcycle || 0) + (counts.bus || 0) + (counts.truck || 0);
    updateSummary();
  }

  start.addEventListener('click', async () => {
    await fetch(`/api/reset/${feed.session_id}`, { method: 'POST' });
    img.src = `${feed.stream_url}?run=${Date.now()}`;
    img.style.display = 'block';
    empty.style.display = 'none';
    badge.textContent = 'LIVE';
    badge.classList.add('live');
    stop.disabled = false;
    feed.live = true;
    timer = setInterval(refreshCounts, 500);
    refreshCounts();
  });

  stop.addEventListener('click', () => {
    img.removeAttribute('src');
    img.style.display = 'none';
    empty.style.display = 'block';
    badge.textContent = 'STOPPED';
    badge.classList.remove('live');
    stop.disabled = true;
    feed.live = false;
    clearInterval(timer);
    updateSummary();
  });

  root.querySelector('.zone').addEventListener('click', () => openZoneModal(feed));
  $('camera-grid').appendChild(root);
  renderZoneCameraOptions();
}

async function loadEvents(page = 0) {
  const events = await fetch('/events?limit=500').then((response) => response.json());
  window.eventData = events;
  renderEvents($('event-list'), events, page, eventPageSize, loadEvents);
  updateSummary();
}

function layout() {
  document.querySelector('#app').innerHTML = `
    <div class="app-layout">
      <aside id="sidebar"></aside>
      <main class="main">
        <header class="topbar">
          <div>
            <label>OPERATIONS CENTER</label>
            <h1>Dashboard</h1>
            <p>Live camera intelligence and detection activity.</p>
          </div>
          <span class="health">All systems operational</span>
        </header>

        <input id="files" type="file" accept="video/*" multiple hidden>
        <p id="notice"></p>

        <section class="view active" data-view="overview">
          <section class="kpis">
            <div><small>Active cameras</small><b id="active">0</b></div>
            <div><small>People visible</small><b id="people">0</b></div>
            <div><small>Vehicles visible</small><b id="vehicles">0</b></div>
            <div><small>Events</small><b id="events-count">0</b></div>
          </section>
          <div class="overview-grid">
            <section class="overview-panel">
              <h2>System overview</h2>
              <p>Monitor active camera feeds, current object counts, and recent detection activity.</p>
              <button class="primary" id="overview-add-camera" type="button">Add camera</button>
            </section>
            <section class="overview-panel">
              <h2>Zone setup</h2>
              <p>Create zones by clicking points directly on the camera frame. The saved polygon uses exact video coordinates.</p>
              <button class="ghost" id="overview-zones" type="button">Open zones</button>
            </section>
          </div>
        </section>

        <section class="view" data-view="cameras">
          <div class="toolbar">
            <div>
              <h2>Camera feeds</h2>
              <p>Start detection independently for each source.</p>
            </div>
            <button class="primary" id="add-camera-main" type="button">Add cameras</button>
          </div>
          <section id="camera-grid" class="camera-grid"></section>
        </section>

        <section class="view" data-view="zones">
          <div class="zone-panel">
            <div>
              <h2>Zones</h2>
              <p>Choose a camera, then click points on the video frame to create a polygon.</p>
            </div>
            <button class="ghost" id="create-zone" type="button">Create zone</button>
          </div>
          <section class="zone-camera-list" id="zone-camera-list"></section>
        </section>

        <section class="view" data-view="events">
          <div class="section-head">
            <div>
              <h2>Recent events</h2>
              <p>Latest detection activity.</p>
            </div>
            <button class="ghost" id="refresh" type="button">Refresh</button>
          </div>
          <section id="event-list"></section>
        </section>
      </main>
    </div>
    <div id="modal-root"></div>
  `;
}

function renderZoneCameraOptions() {
  const root = $('zone-camera-list');
  if (!root) return;

  if (!feeds.length) {
    root.innerHTML = '<div class="empty-panel"><b>No cameras added</b><small>Add a camera before creating zones.</small></div>';
    return;
  }

  root.innerHTML = feeds.map((feed, index) => `
    <article class="zone-camera">
      <div>
        <small>CAMERA ${index + 1}</small>
        <h3>${feed.filename}</h3>
      </div>
      <button class="ghost" type="button" data-zone-camera="${index}">Draw zone</button>
    </article>
  `).join('');

  root.querySelectorAll('[data-zone-camera]').forEach((button) => {
    button.addEventListener('click', () => openZoneModal(feeds[Number(button.dataset.zoneCamera)]));
  });
}

function bindSidebar() {
  const sidebar = $('sidebar');
  const fileInput = $('files');

  sidebar.querySelector('[data-action="add-camera"]').addEventListener('click', () => {
    fileInput.click();
  });

  sidebar.querySelectorAll('[data-target]').forEach((link) => {
    link.addEventListener('click', () => {
      setActiveView(link.dataset.target);
    });
  });
}

layout();
renderSidebar($('sidebar'));
bindSidebar();

$('refresh').addEventListener('click', () => loadEvents(0));
$('overview-add-camera').addEventListener('click', () => {
  setActiveView('cameras');
  $('files').click();
});
$('overview-zones').addEventListener('click', () => setActiveView('zones'));
$('add-camera-main').addEventListener('click', () => $('files').click());
$('create-zone').addEventListener('click', () => {
  if (!feeds.length) {
    $('notice').textContent = 'Upload a camera feed before creating a zone.';
    $('files').click();
    return;
  }
  openZoneModal(feeds[0]);
});

$('files').addEventListener('change', async (event) => {
  const remainingSlots = 2 - feeds.length;
  const selectedFiles = Array.from(event.target.files).slice(0, remainingSlots);

  for (const file of selectedFiles) {
    const body = new FormData();
    body.append('file', file);
    const upload = await fetch('/api/uploads', { method: 'POST', body }).then((response) => response.json());
    feeds.push({ ...upload, filename: file.name, live: false });
    addCard(feeds[feeds.length - 1], feeds.length - 1);
  }

  $('notice').textContent = feeds.length >= 2 ? 'Two camera feeds are ready.' : 'Camera feed ready.';
  event.target.value = '';
  updateSummary();
});

loadEvents();
renderZoneCameraOptions();
