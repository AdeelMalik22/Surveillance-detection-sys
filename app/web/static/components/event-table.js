function eventTime(value) {
  if (!value) return 'Unknown time';
  return new Date(value).toLocaleString();
}

function eventCamera(value) {
  return String(value || 'camera').slice(0, 12);
}

export function renderEvents(root, events = [], page = 0, pageSize = 10, onPage = () => {}) {
  if (!events.length) {
    root.innerHTML = '<div class="empty-panel"><b>No events yet</b><small>Detection activity will appear here.</small></div>';
    return;
  }

  const totalPages = Math.max(1, Math.ceil(events.length / pageSize));
  const currentPage = Math.min(Math.max(page, 0), totalPages - 1);
  const start = currentPage * pageSize;
  const visibleEvents = events.slice(start, start + pageSize);
  const end = Math.min(start + visibleEvents.length, events.length);

  root.innerHTML = `
    <div class="event-table">
      <div class="event-row event-header">
        <span>Object</span>
        <span>Camera</span>
        <span>Zone</span>
        <span>Timestamp</span>
      </div>
      ${visibleEvents.map((event) => `
        <div class="event-row">
          <b>${event.object_class || 'object'}</b>
          <span>${eventCamera(event.camera_id)}</span>
          <span>${event.zone_id || 'unassigned'}</span>
          <time>${eventTime(event.timestamp)}</time>
        </div>
      `).join('')}
    </div>
    <div class="pagination">
      <span>${start + 1}-${end} of ${events.length}</span>
      <div>
        <button type="button" data-page="prev" ${currentPage === 0 ? 'disabled' : ''}>Previous</button>
        <strong>Page ${currentPage + 1} of ${totalPages}</strong>
        <button type="button" data-page="next" ${currentPage >= totalPages - 1 ? 'disabled' : ''}>Next</button>
      </div>
    </div>
  `;

  root.querySelector('[data-page="prev"]')?.addEventListener('click', () => onPage(currentPage - 1));
  root.querySelector('[data-page="next"]')?.addEventListener('click', () => onPage(currentPage + 1));
}
