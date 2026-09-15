export function renderSidebar(root) {
  root.innerHTML = `
    <div class="side-brand">
      <b>SV</b>
      <strong>Sentinel Vision<small>AI surveillance</small></strong>
    </div>
    <button class="side-add-camera" type="button" data-action="add-camera">
      <span>+</span>Add camera
    </button>
    <nav aria-label="Dashboard navigation">
      <button class="side-link active" type="button" data-target="overview">Dashboard</button>
      <button class="side-link" type="button" data-target="cameras">Cameras</button>
      <button class="side-link" type="button" data-target="events">Events</button>
      <button class="side-link" type="button" data-target="zones">Zones</button>
    </nav>
    <small class="side-note">Local workspace · v0.1.0</small>
  `;
}
