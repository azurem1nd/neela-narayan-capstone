/* Track Record — 3D turntable hero graphic.
   Disc surface is a realistic reflective/prismatic finish (rainbow
   diffraction streaks over a silver base, glossy clearcoat) modeled
   after a burned CD's iridescent look — physically-based iridescence
   plus an art-directed streak texture, not the brushed-metal/chrome
   treatment used for the platter and tonearm. Static when logged
   out, begins a slow continuous spin once the session is connected
   (driven by the `data-spinning` attribute the template sets from
   the same `logged_in` flag used everywhere else). */

import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const container = document.getElementById('turntable-3d');

if (container && window.WebGLRenderingContext) {
  try {
    initTurntable(container);
  } catch (err) {
    console.error('turntable3d: failed to init', err);
  }
}

// Art-directed disc surface: silver base + fine radiating rainbow
// streaks (diffraction-like, per the burncd.app reference) plus faint
// concentric micro-grooves for sparkle. Combined at render time with
// MeshPhysicalMaterial's physical `iridescence` for a real angle-
// dependent shimmer on top of the baked pattern.
function makeIridescentDiscTexture() {
  const size = 1024;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const cx = size / 2;
  const cy = size / 2;
  const R = size * 0.5;

  const base = ctx.createRadialGradient(cx, cy, R * 0.12, cx, cy, R);
  base.addColorStop(0, '#eef1f4');
  base.addColorStop(0.6, '#9297a1');
  base.addColorStop(1, '#63676f');
  ctx.fillStyle = base;
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, Math.PI * 2);
  ctx.fill();

  const streakCount = 300;
  for (let i = 0; i < streakCount; i++) {
    const angle = (i / streakCount) * Math.PI * 2 + Math.random() * 0.02;
    const hue = (i * 53) % 360;
    const innerR = R * (0.16 + Math.random() * 0.06);
    const outerR = R * (0.76 + Math.random() * 0.23);
    const x0 = cx + Math.cos(angle) * innerR;
    const y0 = cy + Math.sin(angle) * innerR;
    const x1 = cx + Math.cos(angle) * outerR;
    const y1 = cy + Math.sin(angle) * outerR;
    const grad = ctx.createLinearGradient(x0, y0, x1, y1);
    grad.addColorStop(0, `hsla(${hue}, 100%, 55%, 0)`);
    grad.addColorStop(0.5, `hsla(${hue}, 100%, 58%, 0.95)`);
    grad.addColorStop(1, `hsla(${(hue + 45) % 360}, 100%, 55%, 0)`);
    ctx.strokeStyle = grad;
    ctx.lineWidth = 1.4 + Math.random() * 3;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
  }

  for (let r = R * 0.2; r < R * 0.98; r += 1.6) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(255, 255, 255, ${(r % 6 < 3) ? 0.05 : 0.02})`;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function initTurntable(container) {
  const isSpinning = container.dataset.spinning === 'true';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const spinning = isSpinning && !reduceMotion;

  const scene = new THREE.Scene();

  const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
  camera.position.set(0.4, 2.7, 5.4);
  camera.lookAt(0, -0.1, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  // Soft studio environment for real chrome reflections (IBL), kept out
  // of the visible background so the page's cream backdrop shows through.
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.035).texture;

  const ambient = new THREE.AmbientLight(0xffffff, 0.35);
  scene.add(ambient);

  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(3, 5.5, 4);
  scene.add(key);

  const rim = new THREE.PointLight(0xbcd6ff, 0.85, 18);
  rim.position.set(-4, 2, -3);
  scene.add(rim);

  const warm = new THREE.PointLight(0xfff1d6, 0.55, 18);
  warm.position.set(2.5, -1, 3.5);
  scene.add(warm);

  // Third color pulled from the brand accent, positioned as a tight
  // glint so it adds a magenta note to the highlights without
  // tinting the whole disc surface.
  const accent = new THREE.PointLight(0xf253ad, 0.65, 14);
  accent.position.set(-2, -1.5, 4);
  scene.add(accent);

  const chrome = new THREE.MeshPhysicalMaterial({
    color: 0xdadde1,
    metalness: 1,
    roughness: 0.16,
    clearcoat: 0.6,
    clearcoatRoughness: 0.18,
  });

  const brushedSilver = new THREE.MeshStandardMaterial({
    color: 0xc6cad0,
    metalness: 0.95,
    roughness: 0.36,
  });

  const discMat = new THREE.MeshPhysicalMaterial({
    color: 0xffffff,
    map: makeIridescentDiscTexture(),
    metalness: 0.75,
    roughness: 0.06,
    iridescence: 0.8,
    iridescenceIOR: 1.4,
    iridescenceThicknessRange: [120, 580],
    clearcoat: 1,
    clearcoatRoughness: 0.03,
  });

  const labelMat = new THREE.MeshPhysicalMaterial({
    color: 0xe6e9ec,
    metalness: 1,
    roughness: 0.14,
    clearcoat: 0.5,
  });

  const rig = new THREE.Group();
  rig.rotation.x = -0.1;
  rig.scale.setScalar(0.84);
  scene.add(rig);

  const plinth = new THREE.Mesh(new THREE.CylinderGeometry(2.3, 2.36, 0.16, 72), brushedSilver);
  plinth.position.y = -0.28;
  rig.add(plinth);

  const platter = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.0, 0.1, 72), chrome);
  platter.position.y = -0.15;
  rig.add(platter);

  const spinGroup = new THREE.Group();
  spinGroup.position.y = -0.08;
  rig.add(spinGroup);

  const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.78, 1.78, 0.04, 72), discMat);
  spinGroup.add(disc);

  const label = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.05, 48), labelMat);
  label.position.y = 0.005;
  spinGroup.add(label);

  const spindle = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.22, 24), chrome);
  spindle.position.y = 0.02;
  rig.add(spindle);

  // Tonearm: base mount + pivoting shaft with a headshell at the tip.
  const armBase = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.22, 0.2, 32), chrome);
  armBase.position.set(1.62, -0.18, -1.55);
  rig.add(armBase);

  const armGroup = new THREE.Group();
  armGroup.position.set(1.62, -0.02, -1.55);
  armGroup.rotation.y = spinning ? -0.62 : -0.22;
  rig.add(armGroup);

  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.042, 0.05, 2.05, 20), chrome);
  shaft.geometry.rotateZ(Math.PI / 2);
  shaft.geometry.translate(-1.02, 0, 0);
  armGroup.add(shaft);

  const headshell = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.07, 0.3), brushedSilver);
  headshell.position.set(-2.02, -0.02, 0);
  armGroup.add(headshell);

  const counterweight = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.13, 0.16, 20), chrome);
  counterweight.rotation.z = Math.PI / 2;
  counterweight.position.set(0.32, 0.05, 0);
  armGroup.add(counterweight);

  function resize() {
    const size = container.clientWidth;
    if (!size) return;
    renderer.setSize(size, size);
    camera.aspect = 1;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  resize();

  function animate() {
    requestAnimationFrame(animate);
    if (spinning) {
      spinGroup.rotation.y += 0.0055;
    }
    container.dataset.spinRotation = spinGroup.rotation.y.toFixed(4);
    renderer.render(scene, camera);
  }
  animate();
}
