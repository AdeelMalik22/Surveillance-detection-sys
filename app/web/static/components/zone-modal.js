function drawPolygon(canvas, points, hoverPoint = null) {
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);

  if (!points.length) return;

  context.lineWidth = 3;
  context.strokeStyle = '#74dfbb';
  context.fillStyle = 'rgba(116, 223, 187, 0.16)';
  context.beginPath();
  points.forEach(([x, y], index) => {
    if (index === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  });
  if (hoverPoint) context.lineTo(hoverPoint[0], hoverPoint[1]);
  if (points.length >= 3 && !hoverPoint) context.closePath();
  context.stroke();
  if (points.length >= 3 && !hoverPoint) context.fill();

  points.forEach(([x, y], index) => {
    context.fillStyle = '#74dfbb';
    context.beginPath();
    context.arc(x, y, 5, 0, Math.PI * 2);
    context.fill();
    context.fillStyle = '#061017';
    context.font = '11px Inter, sans-serif';
    context.fillText(String(index + 1), x - 3, y + 4);
  });
}

function scalePoint(event, canvas, image) {
  const rect = canvas.getBoundingClientRect();
  const displayX = event.clientX - rect.left;
  const displayY = event.clientY - rect.top;
  const sourceWidth = image.naturalWidth || rect.width;
  const sourceHeight = image.naturalHeight || rect.height;

  return [
    Math.round((displayX / rect.width) * sourceWidth),
    Math.round((displayY / rect.height) * sourceHeight),
  ];
}

function displayPoint(point, canvas, image) {
  const rect = canvas.getBoundingClientRect();
  const sourceWidth = image.naturalWidth || rect.width;
  const sourceHeight = image.naturalHeight || rect.height;

  return [
    Math.round((point[0] / sourceWidth) * canvas.width),
    Math.round((point[1] / sourceHeight) * canvas.height),
  ];
}

function renderPointList(root, points) {
  root.innerHTML = points.length
    ? points.map(([x, y], index) => `<code>${index + 1}. [${x}, ${y}]</code>`).join('')
    : '<span>No points selected</span>';
}

export function openZoneModal(feed) {
  const root = document.querySelector('#modal-root');
  const points = [];
  let displayPoints = [];

  root.innerHTML = `
    <div class="modal-bg">
      <div class="modal zone-modal">
        <header>
          <div>
            <h2>Add zone</h2>
            <p>${feed.filename}</p>
          </div>
          <button id="close-modal" type="button">x</button>
        </header>
        <form id="zone-form">
          <div class="zone-body">
            <label>
              Zone name
              <input name="id" placeholder="restricted_area" required>
            </label>
            <div class="zone-drawer">
              <img id="zone-frame" src="${feed.stream_url}?zone=${Date.now()}" alt="Camera frame for zone drawing">
              <canvas id="zone-canvas"></canvas>
            </div>
            <div class="zone-tools">
              <button class="ghost" id="undo-zone-point" type="button">Undo point</button>
              <button class="ghost" id="clear-zone-points" type="button">Clear</button>
              <span>Click at least 3 points on the frame.</span>
            </div>
            <div class="zone-points" id="zone-points"></div>
            <input name="polygon" id="zone-polygon" type="hidden" required>
          </div>
          <div class="zone-footer">
            <span id="zone-status">0 points selected</span>
            <button type="submit">Save zone</button>
          </div>
        </form>
      </div>
    </div>
  `;

  const image = document.querySelector('#zone-frame');
  const canvas = document.querySelector('#zone-canvas');
  const pointList = document.querySelector('#zone-points');
  const polygonInput = document.querySelector('#zone-polygon');
  const status = document.querySelector('#zone-status');

  function syncCanvas() {
    const rect = image.getBoundingClientRect();
    canvas.width = Math.round(rect.width);
    canvas.height = Math.round(rect.height);
    displayPoints = points.map((point) => displayPoint(point, canvas, image));
    drawPolygon(canvas, displayPoints);
    polygonInput.value = points.length >= 3 ? JSON.stringify(points) : '';
    status.textContent = `${points.length} point${points.length === 1 ? '' : 's'} selected`;
    renderPointList(pointList, points);
  }

  document.querySelector('#close-modal').addEventListener('click', () => {
    root.innerHTML = '';
  });

  image.addEventListener('load', syncCanvas);
  window.addEventListener('resize', syncCanvas, { once: true });

  canvas.addEventListener('click', (event) => {
    points.push(scalePoint(event, canvas, image));
    syncCanvas();
  });

  canvas.addEventListener('mousemove', (event) => {
    if (!points.length) return;
    const rect = canvas.getBoundingClientRect();
    drawPolygon(canvas, displayPoints, [event.clientX - rect.left, event.clientY - rect.top]);
  });

  canvas.addEventListener('mouseleave', syncCanvas);

  document.querySelector('#undo-zone-point').addEventListener('click', () => {
    points.pop();
    syncCanvas();
  });

  document.querySelector('#clear-zone-points').addEventListener('click', () => {
    points.length = 0;
    syncCanvas();
  });

  document.querySelector('#zone-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (points.length < 3) return;

    const form = new FormData(event.target);
    const response = await fetch('/zones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        camera_id: feed.session_id,
        zone: {
          id: form.get('id'),
          polygon: points,
        },
      }),
    });

    if (response.ok) {
      const savedZone = await response.json();
      feed.zones = [...(feed.zones || []).filter((zone) => zone.id !== savedZone.id), savedZone];
      root.innerHTML = '';
    }
    else alert('Unable to save zone');
  });

  renderPointList(pointList, points);
}
