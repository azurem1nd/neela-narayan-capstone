/* Track Record — 3D chrome turntable hero graphic.
   Static when logged out, begins a slow continuous spin once the
   session is connected (driven by the `data-spinning` attribute the
   template sets from the same `logged_in` flag used everywhere else). */

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

function makeGrooveTexture() {
  const size = 512;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#0b0b0d';
  ctx.fillRect(0, 0, size, size);
  const cx = size / 2;
  const cy = size / 2;
  for (let r = size * 0.14; r < size * 0.495; r += 2.4) {
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(255, 255, 255, ${(r % 7.2 < 3.6) ? 0.06 : 0.025})`;
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

  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(3, 5.5, 4);
  scene.add(key);

  const rim = new THREE.PointLight(0xbcd6ff, 1.2, 24);
  rim.position.set(-4, 2, -3);
  scene.add(rim);

  const warm = new THREE.PointLight(0xfff1d6, 0.7, 24);
  warm.position.set(2.5, -1, 3.5);
  scene.add(warm);

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

  const vinylMat = new THREE.MeshStandardMaterial({
    color: 0x0e0e10,
    metalness: 0.25,
    roughness: 0.42,
    map: makeGrooveTexture(),
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

  const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.78, 1.78, 0.04, 72), vinylMat);
  spinGroup.add(disc);

  const label = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.52, 0.05, 48), labelMat);
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
