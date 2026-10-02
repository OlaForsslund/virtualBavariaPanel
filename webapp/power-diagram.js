// The power-flow diagram, shared by the app and the dev pages: plain globals, no
// dependency on index.html. Usage:
//   const f = computePowerFigures(electrical, solarLoadLabel);
//   mount.innerHTML = powerDiagramSvg(f, 'some-unique-id');
// The SVG is a 400x400 viewBox; size it with CSS (width, height:auto).

// Instance keys aren't fixed: the boat's Victron BLE integration uses
// '1'/'0', but Venus OS's own dbus->Signal K bridge assigns its own
// instance numbers (e.g. '256') -- discover instead of hardcoding.
// Shared by renderPower and the Config tab's "Test connection" button.
function pickElectricalInstances(elec) {
  // Solar: every instance present, not just one -- a real multi-MPPT
  // boat can have more than one charge controller, and Venus's own demo
  // data does too. Object.keys() on numeric-string keys like "256"/"258"
  // iterates in ascending numeric order regardless of insertion order,
  // so this is deterministic.
  const solarKeys = elec.solar ? Object.keys(elec.solar) : [];
  // Batteries: multiple instances are normal (house, starter, hydropack,
  // alternator-derived...). Prefer one named "house"; otherwise the first
  // instance that actually has power data (excludes alternator-only
  // entries and the "-second"-suffixed secondary-voltage-only taps).
  const battKeys = elec.batteries ? Object.keys(elec.batteries) : [];
  const battKey = battKeys.find(k => /house/i.test((elec.batteries[k].name || {}).value || ''))
    || battKeys.find(k => elec.batteries[k].power);
  return { solarKeys, battKey };
}

// Derived figures, computed once per update and rendered twice -- the
// Power page and the Overview draw the identical diagram, so the maths
// lives here rather than in either renderer.
function computePowerFigures(elec, solarLoadLabel) {
  const { solarKeys, battKey } = pickElectricalInstances(elec);
  const solarList = solarKeys.map(k => elec.solar[k]);
  const batt = battKey ? elec.batteries[battKey] : null;

  // Prefer the battery-side "current" reading; some chargers (seen in
  // Venus's own demo data) only publish "panelCurrent" (the panel-side
  // reading, upstream of the MPPT conversion) instead -- not quite the
  // same physical quantity, but the closest approximation available
  // when the battery-side figure isn't published for that instance.
  const solarInstanceCurrent = (s) => (s.current && s.current.value) || (s.panelCurrent && s.panelCurrent.value) || 0;
  const solarInstancePower = (s) => (s.panelPower && s.panelPower.value) || 0;

  // The controller's own load output -- a separate pair of terminals on
  // the MPPT, NOT part of the boat's DC distribution, so it is emphatically
  // not the LOAD node below. Here it feeds the always-on IP gear (router +
  // Pi) directly off the controller.
  //
  // Unlike LOAD this is a real measurement (loadCurrent x the controller's
  // own bus voltage), which is why it may honestly show a wattage. null --
  // not 0 -- when no instance publishes loadCurrent at all, so a controller
  // without the feature stays blank rather than claiming a measured zero.
  // Prefer the published loadPower: it is the product of two fields from
  // a single advertisement, so it is a true instantaneous figure. Fall
  // back to loadCurrent x the controller's own bus voltage for sources
  // that do not publish it.
  // The controller's load output (e.g. NAUTICORE): from the first controller that reports one.
  const solarLoadIndex = solarList.findIndex(s => (s.loadPower && typeof s.loadPower.value === 'number')
    || (s.loadCurrent && typeof s.loadCurrent.value === 'number'));
  const loadSolar = solarList[solarLoadIndex];
  const solarLoadWatts = !loadSolar ? null
    : typeof (loadSolar.loadPower && loadSolar.loadPower.value) === 'number' ? loadSolar.loadPower.value
    : loadSolar.loadCurrent.value * ((loadSolar.voltage && loadSolar.voltage.value) || 12);
  const totalSolarCurrent = solarList.reduce((sum, s) => sum + solarInstanceCurrent(s), 0);

  // Infer charger power: battery current - total solar current (summed
  // across every solar instance). If positive, something other than
  // solar is supplying power -- could be a land/shore charger, could be
  // the engine alternator.
  const battCurrent = (batt && batt.current && batt.current.value) || 0;
  let chargerCurrent = battCurrent - totalSolarCurrent;
  if (chargerCurrent < 2) chargerCurrent = 0; // 2 A deadband for chargers
  const battVoltage = (batt && batt.voltage && batt.voltage.value) || 12;
  const chargerPower = battVoltage * chargerCurrent;

  // Load has no sensor of its own -- only battery and solar are actually
  // measured (the charger figure above is already an inference, not a
  // reading). A load *number* would be a further inference stacked on
  // top of that inferred charger figure, compounding its error, so it's
  // deliberately not shown -- only the direction/shape of the diagram
  // (solar/charger feed the center, battery makes up the difference)
  // reflects the "load" concept; no wattage is claimed for it.
  const battPower = (batt && batt.power && batt.power.value) || 0;
  // Bus load = what solar and battery put in; unknown while a charger/alternator also feeds it.
  const loadCurrent = totalSolarCurrent - battCurrent;
  const loadPower = chargerCurrent === 0 && loadCurrent >= 0 ? loadCurrent * battVoltage : null;

  // Victron's own convention (BMV/SmartShunt, confirmed against real
  // hardware) is the opposite of the generic Signal K schema text:
  // positive = charging (current into the battery), negative =
  // discharging (current out) -- not "+ve out" as the spec description
  // for electrical.batteries.*.current literally says.
  const battDischarging = battCurrent < -0.5; // negative -- supplying the load's shortfall
  const battCharging = battCurrent > 0.5;     // positive -- absorbing the load's surplus

  return {
    solarLoadWatts, solarLoadIndex, solarLoadLabel: solarLoadLabel || '',
    solarList, batt, battCurrent, battVoltage, battPower,
    chargerCurrent, chargerPower, loadPower, battDischarging, battCharging,
    solarInstancePower, solarInstanceCurrent,
    // Amp-hours taken out of the bank since it was last full, published
    // in Ah and positive (bt-sensors reads the shunt's raw unsigned
    // magnitude straight through). Sign is left exactly as published.
    dischargeSinceFull: (batt && batt.capacity && batt.capacity.ampHoursConsumed && batt.capacity.ampHoursConsumed.value),
    soc: ((batt && batt.capacity && batt.capacity.stateOfCharge && batt.capacity.stateOfCharge.value) || 0) * 100,
    hoursRemaining: ((batt && batt.capacity && batt.capacity.timeRemaining && batt.capacity.timeRemaining.value) || 0) / 3600,
  };
}

// Solar boxes run down the left: first at the top, last ending `bottom`, gaps even.
const POWER_BOX_W = 125; // width shared by solar, charger, load-output, load (diameter) and battery
const POWER_LOAD = { cx: 265, cy: 200, r: POWER_BOX_W / 2 };
const SOLAR_TOP = 10, LOAD_OUT_Y = 347, LOAD_OUT_ARROW = 56; // load-output box bottom lines up with the battery's
function solarBoxLayout(count, bottom) {
  const h = 70;
  // One box sits at the bottom; several span top to bottom with even gaps.
  if (count === 1) return [{ x: 10, w: POWER_BOX_W, h, y: bottom - h }];
  const gap = (bottom - SOLAR_TOP - count * h) / (count - 1);
  return Array.from({ length: count }, (_, i) => ({ x: 10, w: POWER_BOX_W, h, y: SOLAR_TOP + i * (h + gap) }));
}

// The diagram, drawn identically by the Power page and the Overview.
// `id` scopes the element *and* its arrowhead marker: both render into
// the same document, and a duplicate marker id would leave the second
// diagram's url(#...) references resolving to the first one's marker.
function powerDiagramSvg(f, id) {
  const solarLoadLabel = f.solarLoadLabel || '';
  const marker = `${id}-arrowhead`;
  const T = 'var(--text-primary)';
  const LOAD = POWER_LOAD, X = LOAD.cx;
  const SOLAR_DEADBAND_A = 0.05; // measured, unlike the inferred charger current
  const solarList = f.solarList;
  const chargerCurrent = f.chargerCurrent;
  const chargerOn = chargerCurrent > 0;
  const solarLoadWatts = f.solarLoadWatts;
  const showSolarLoad = !!solarLoadLabel && typeof solarLoadWatts === 'number';
  const layout = solarBoxLayout(Math.max(1, solarList.length), showSolarLoad ? LOAD_OUT_Y - LOAD_OUT_ARROW : 397);
  // Filled bottom-up (SOLAR 1 at the bottom, later ones above), except the controller with the
  // load output always goes last (bottom), so its load line doesn't cross another box.
  const solarOrder = solarList.map((s, i) => i).reverse();
  if (f.solarLoadIndex > -1) solarOrder.splice(solarOrder.indexOf(f.solarLoadIndex), 1), solarOrder.push(f.solarLoadIndex);
  const solarNodesSvg = (solarList.length ? solarOrder : [null]).map((n, i) => {
    const s = n === null ? null : solarList[n];
    const L = layout[i];
    const power = s ? f.solarInstancePower(s) : 0;
    const current = s ? f.solarInstanceCurrent(s) : 0;
    const label = solarList.length > 1 ? `SOLAR ${n + 1}` : 'SOLAR';
    const sy = L.y + L.h / 2;
    // Each arrow lands at its own spot on the circle's left arc, heading for the centre, so the heads don't stack.
    const cnt = layout.length, ang = (cnt > 1 ? -40 + 80 * i / (cnt - 1) : 25) * Math.PI / 180;
    const px = (k) => (LOAD.cx - k * Math.cos(ang)).toFixed(1), py = (k) => (LOAD.cy + k * Math.sin(ang)).toFixed(1);
    const end = `${px(LOAD.r + 2)} ${py(LOAD.r + 2)}`, ctrl = `${px(LOAD.r + 36)} ${py(LOAD.r + 36)}`;
    const d = current < -SOLAR_DEADBAND_A ? `M ${end} Q ${ctrl} ${L.x + L.w + 2} ${sy}`
                                          : `M ${L.x + L.w} ${sy} Q ${ctrl} ${end}`;
    return `
      <rect x="${L.x}" y="${L.y}" width="${L.w}" height="${L.h}" fill="none" stroke="var(--brass)" stroke-width="2" rx="4"/>
      <text x="${L.x + L.w / 2}" y="${L.y + L.h * 0.3}" class="power-label" fill="${T}">${label}</text>
      <text x="${L.x + L.w / 2}" y="${L.y + L.h * 0.76}" class="power-value" style="font-size:1.5em" fill="${T}">${power.toFixed(0)}W</text>
      <text x="${L.x + L.w + 8}" y="${sy <= LOAD.cy ? sy - 6 : sy + 20}" class="power-amps" style="text-anchor:start" fill="${T}">${current.toFixed(1)}A</text>
      <path d="${d}" class="arrow-${Math.abs(current) > SOLAR_DEADBAND_A ? 'active arrow-flowing' : 'inactive'}" fill="none" marker-end="url(#${marker})"/>
    `;
  }).join('');

  // The controller's load output: its own box under the last solar box,
  // deliberately never touching the LOAD circle -- these terminals bypass
  // the boat's DC distribution entirely, and a line into LOAD would claim
  // a connection that doesn't exist. Drawn only when a label is configured
  // AND the controller actually publishes the figure.
  const last = layout[layout.length - 1];
  // Box grows with the free-text label, centred under the solar box; fixed width; the text shrinks to fit.
  const loadLabelW = solarLoadLabel.length * 11; // ~11 units/char at .power-label size
  const loadBoxW = POWER_BOX_W;
  const solarCx = last.x + last.w / 2;
  const loadBoxX = Math.max(2, solarCx - loadBoxW / 2);
  const loadBoxCx = loadBoxX + loadBoxW / 2;
  const loadLabelEm = (1.05 * Math.min(1, (loadBoxW - 12) / Math.max(1, loadLabelW))).toFixed(2);
  const solarLoadSvg = !showSolarLoad ? '' : `
      <path d="M ${solarCx} ${last.y + last.h} L ${loadBoxCx} ${LOAD_OUT_Y - 2}"
            class="arrow-${solarLoadWatts > 0 ? 'active arrow-flowing' : 'inactive'}" fill="none" marker-end="url(#${marker})"/>
      <rect x="${loadBoxX}" y="${LOAD_OUT_Y}" width="${loadBoxW}" height="50" rx="4"
            fill="none" stroke="${solarLoadWatts > 0 ? 'var(--brass)' : 'var(--text-secondary)'}" stroke-width="2"/>
      <text x="${loadBoxCx}" y="${LOAD_OUT_Y + 16}" class="power-label" style="font-size:${loadLabelEm}em" fill="${T}">${solarLoadLabel.replace(/[&<>"']/g, (c) => '&#' + c.charCodeAt(0) + ';')}</text>
      <text x="${loadBoxCx}" y="${LOAD_OUT_Y + 41}" class="power-value" fill="${T}">${solarLoadWatts.toFixed(0)}W</text>
  `;

  // Arrowhead direction follows the path's own direction. Discharging
  // (neg): arrow from battery to load. Charging (pos): the reverse.
  const battTop = 338; // top edge of the battery's terminals
  const battArrowPath = f.battDischarging ? `M ${X} ${battTop} L ${X} ${LOAD.cy + LOAD.r + 2}` : `M ${X} ${LOAD.cy + LOAD.r} L ${X} ${battTop - 2}`;
  const battArrowClass = (f.battDischarging || f.battCharging) ? 'arrow-active arrow-flowing' : 'arrow-inactive';
  const chargerArrowClass = `arrow-${chargerOn ? 'active arrow-flowing' : 'inactive'}`;

  return `
    <svg viewBox="0 0 400 400" id="${id}" class="power-diagram">
      ${solarNodesSvg}
      ${solarLoadSvg}

      <!-- Charger / alternator, centred above LOAD; 16px bold ALTERNATOR is ~119 wide in the 140 box; its figures are inferred, so they sit on its battery line -->
      <rect x="${X - POWER_BOX_W / 2}" y="10" width="${POWER_BOX_W}" height="64" fill="none" stroke="${chargerOn ? 'var(--brass)' : 'var(--text-secondary)'}" stroke-width="2" rx="4"/>
      <text x="${X}" y="36" class="power-label" style="font-size:15px" fill="${T}">CHARGER /</text>
      <text x="${X}" y="58" class="power-label" style="font-size:15px" fill="${T}">ALTERNATOR</text>
      <path d="M ${X} 76 L ${X} ${LOAD.cy - LOAD.r - 2}" class="${chargerArrowClass}" fill="none" marker-end="url(#${marker})"/>
      <!-- Charger -> battery: forks off the stem at y=90, passes right of LOAD, merges into the battery line at y=305 -->
      <path d="M ${X} 90 C ${X} 130, ${X + 96} 150, ${X + 96} 200 C ${X + 96} 250, ${X} 265, ${X} 305" class="${chargerArrowClass}" fill="none"/>
      ${chargerOn ? `<text x="${X + 79}" y="124" class="power-label" style="font-size:0.8em;text-anchor:start" fill="${T}">Charge</text><text x="${X + 79}" y="140" class="power-amps" style="text-anchor:start" fill="${T}">${chargerCurrent.toFixed(1)}A</text><text x="${X + 79}" y="156" class="power-value" style="text-anchor:start" fill="${T}">${f.chargerPower.toFixed(0)}W</text>` : ''}

      <!-- Load: fed by solar, battery and charger; wattage only when no charger is active -->
      <circle cx="${LOAD.cx}" cy="${LOAD.cy}" r="${LOAD.r}" fill="none" stroke="var(--brass)" stroke-width="3"/>
      ${f.loadPower === null
        ? `<text x="${LOAD.cx}" y="${LOAD.cy + 6}" class="power-label" style="font-size:1.3em" fill="${T}">LOAD</text>`
        : `<text x="${LOAD.cx}" y="${LOAD.cy - 4}" class="power-label" style="font-size:1.3em" fill="${T}">LOAD</text><text x="${LOAD.cx}" y="${LOAD.cy + 22}" class="power-value" fill="${T}">${f.loadPower.toFixed(0)}W</text>`}

      <!-- Arrow: Battery <-> Load -- direction flips with which way current is flowing -->
      <path d="${battArrowPath}" class="${battArrowClass}" fill="none" marker-end="url(#${marker})"/>
      <text x="${X + 12}" y="326" class="power-amps" style="text-anchor:start" fill="${T}">${Math.abs(f.battCurrent).toFixed(1)}A</text>

      <!-- Battery: body plus terminals, SoC and power inside; the shape names the figure, so no BATTERY label -->
      <g stroke="var(--brass)" stroke-width="2" fill="none">
        <rect x="${X - POWER_BOX_W / 2}" y="345" width="${POWER_BOX_W}" height="52" rx="4"/>
        <rect x="${X - 42}" y="338" width="11" height="7" rx="1.5"/>
        <rect x="${X + 31}" y="338" width="11" height="7" rx="1.5"/>
      </g>
      <text x="${X}" y="369" class="power-soc" fill="${T}">${f.soc.toFixed(0)}%</text>
      <text x="${X}" y="388" class="power-value" fill="${T}">${Math.abs(f.battPower).toFixed(0)}W</text>

      <defs>
        <marker id="${marker}" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
          <polygon points="0 0, 10 3, 0 6" fill="var(--brass)"/>
        </marker>
      </defs>
    </svg>
  `;
}
