"use strict";
(() => {
  const scene = JSON.parse(document.getElementById("scene-data").textContent);
  const canvas = document.getElementById("terrain");
  const status = document.getElementById("viewer-status");
  const notes = document.getElementById("feedback");
  document.getElementById("download-feedback").addEventListener("click", () => {
    if (!notes.value.trim()) {
      document.getElementById("feedback-status").textContent = "Add a note first.";
      notes.focus();
      return;
    }
    const text = `Iteration ${scene.iteration.number}: ${scene.iteration.title}\n\n${notes.value}\n`;
    const url = URL.createObjectURL(new Blob([text], {type: "text/plain;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = `terrain-feedback-${String(scene.iteration.number).padStart(4, "0")}.txt`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    document.getElementById("feedback-status").textContent = "Downloaded. Share this note with your agent.";
  });

  const gl = canvas.getContext("webgl2", {antialias: true, preserveDrawingBuffer: true});
  if (!gl) {
    status.textContent = "Interactive 3D needs WebGL 2. Use the four geometry images below instead.";
    return;
  }
  canvas.addEventListener("webglcontextlost", event => {
    event.preventDefault();
    status.textContent = "The graphics context was lost. Reopen this page, or use the images below.";
  });
  try {
    const vertexSource = `#version 300 es
      in vec3 position;
      uniform mat4 model;
      uniform mat4 viewProjection;
      out vec3 world;
      void main() {
        vec4 p = model * vec4(position, 1.0);
        world = p.xyz;
        gl_Position = viewProjection * p;
      }`;
    const fragmentSource = `#version 300 es
      precision highp float;
      in vec3 world;
      uniform vec3 color;
      uniform bool grid;
      out vec4 pixel;
      void main() {
        if (grid) {
          pixel = vec4(color, 1.0);
        } else {
          vec3 n = normalize(cross(dFdx(world), dFdy(world)));
          float light = 0.44 + 0.40 * abs(dot(n, normalize(vec3(-0.4, -0.5, 1.0))))
                             + 0.16 * abs(dot(n, normalize(vec3(0.7, 0.3, 0.5))));
          pixel = vec4(color * light, 1.0);
        }
      }`;
    const shader = (type, source) => {
      const result = gl.createShader(type);
      gl.shaderSource(result, source);
      gl.compileShader(result);
      if (!gl.getShaderParameter(result, gl.COMPILE_STATUS)) throw Error(gl.getShaderInfoLog(result));
      return result;
    };
    const program = gl.createProgram();
    gl.attachShader(program, shader(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, shader(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw Error(gl.getProgramInfoLog(program));
    gl.useProgram(program);
    const attributes = {position: gl.getAttribLocation(program, "position")};
    const uniforms = Object.fromEntries(
      ["model", "viewProjection", "color", "grid"].map(name => [name, gl.getUniformLocation(program, name)])
    );
    const decode = (value, Type) => {
      const text = atob(value);
      const bytes = new Uint8Array(text.length);
      for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
      return new Type(bytes.buffer);
    };
    const buffer = (target, data) => {
      const result = gl.createBuffer();
      gl.bindBuffer(target, result);
      gl.bufferData(target, data, gl.STATIC_DRAW);
      return result;
    };
    const geometries = new Map(scene.geometry.map(asset => {
      const vertices = decode(asset.vertices, Float32Array);
      const indices = decode(asset.indices, Uint32Array);
      const vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      buffer(gl.ARRAY_BUFFER, vertices);
      gl.enableVertexAttribArray(attributes.position);
      gl.vertexAttribPointer(attributes.position, 3, gl.FLOAT, false, 0, 0);
      buffer(gl.ELEMENT_ARRAY_BUFFER, indices);
      return [asset.id, {vao, count: indices.length}];
    }));
    // Drop encoded geometry after the upload, rather than retaining two CPU copies.
    scene.geometry = null;
    const dataElement = document.getElementById("scene-data");
    dataElement.remove();
    const sub = (a, b) => a.map((v, i) => v - b[i]);
    const dot = (a, b) => a.reduce((s, v, i) => s + v * b[i], 0);
    const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
    const norm = a => a.map(v => v / Math.hypot(...a));
    const multiply = (a, b) => {
      const c = new Float32Array(16);
      for (let col = 0; col < 4; col++)
        for (let row = 0; row < 4; row++)
          for (let k = 0; k < 4; k++) c[col*4+row] += a[k*4+row] * b[col*4+k];
      return c;
    };
    const identity = new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
    const centre = scene.bounds[0].map((v, i) => (v + scene.bounds[1][i]) / 2);
    const radius = Math.max(1, Math.hypot(...sub(scene.bounds[1], scene.bounds[0])) * 0.62);
    let target, yaw, elevation, zoom;
    let activeView = "iso";
    let axes;
    const hidden = new Set();
    const palette = role => {
      if (/objective|focal/.test(role)) return [0.91, 0.70, 0.36];
      if (/cover/.test(role)) return [0.40, 0.73, 0.69];
      return [0.69, 0.77, 0.81];
    };
    const gridPoints = [];
    const gridStep = 50; // Reference ruler only, never an inferred module or gameplay grid.
    const gridRadius = Math.ceil(radius * 1.5 / gridStep) * gridStep;
    const gx = Math.round(centre[0] / gridStep) * gridStep;
    const gy = Math.round(centre[1] / gridStep) * gridStep;
    const gz = scene.bounds[0][2] - 0.1;
    for (let n = -gridRadius; n <= gridRadius; n += gridStep) {
      gridPoints.push(gx+n,gy-gridRadius,gz, gx+n,gy+gridRadius,gz);
      gridPoints.push(gx-gridRadius,gy+n,gz, gx+gridRadius,gy+n,gz);
    }
    const gridVao = gl.createVertexArray();
    gl.bindVertexArray(gridVao);
    buffer(gl.ARRAY_BUFFER, new Float32Array(gridPoints));
    gl.enableVertexAttribArray(attributes.position);
    gl.vertexAttribPointer(attributes.position, 3, gl.FLOAT, false, 0, 0);
    gl.enable(gl.DEPTH_TEST);
    gl.clearColor(0.075, 0.14, 0.19, 1);
    let frame = 0;
    const draw = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * dpr));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * dpr));
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const offset = [
        Math.cos(yaw) * Math.cos(elevation),
        Math.sin(yaw) * Math.cos(elevation),
        Math.sin(elevation),
      ];
      const eye = target.map((v, i) => v + offset[i] * radius * 4);
      const back = norm(sub(eye, target));
      const right = norm(cross([0, 0, 1], back));
      const up = cross(back, right);
      axes = {right, up};
      const view = new Float32Array([
        right[0],up[0],back[0],0, right[1],up[1],back[1],0,
        right[2],up[2],back[2],0, -dot(right,eye),-dot(up,eye),-dot(back,eye),1
      ]);
      const halfHeight = radius / zoom;
      const halfWidth = halfHeight * canvas.width / canvas.height;
      const near = radius * 0.001, far = radius * 20;
      const projection = new Float32Array([
        1/halfWidth,0,0,0, 0,1/halfHeight,0,0, 0,0,-2/(far-near),0,
        0,0,-(far+near)/(far-near),1
      ]);
      gl.uniformMatrix4fv(uniforms.viewProjection, false, multiply(projection, view));
      gl.uniform1i(uniforms.grid, true);
      gl.uniform3fv(uniforms.color, [0.16, 0.26, 0.31]);
      gl.uniformMatrix4fv(uniforms.model, false, identity);
      gl.bindVertexArray(gridVao);
      gl.drawArrays(gl.LINES, 0, gridPoints.length / 3);
      gl.uniform1i(uniforms.grid, false);
      scene.instances.forEach((instance, index) => {
        if (hidden.has(index)) return;
        const geometry = geometries.get(instance.asset);
        gl.bindVertexArray(geometry.vao);
        gl.uniform3fv(uniforms.color, instance.library_status === "custom_unindexed"
          ? [0.78, 0.48, 0.91] : palette(instance.role));
        gl.uniformMatrix4fv(uniforms.model, false, new Float32Array(instance.matrix));
        gl.drawElements(gl.TRIANGLES, geometry.count, gl.UNSIGNED_INT, 0);
      });
      canvas.dataset.frame = String(++frame);
      canvas.dataset.view = activeView;
      canvas.dataset.visiblePieces = String(scene.instances.length - hidden.size);
      status.textContent = `${scene.instances.length - hidden.size} / ${scene.instances.length} pieces visible · 50 mm reference grid · Geometry inspection only`;
      document.querySelectorAll("[data-view]").forEach(button =>
        button.setAttribute("aria-pressed", String(button.dataset.view === activeView))
      );
    };
    const preset = name => {
      target = [...centre];
      zoom = Math.min(1, canvas.clientWidth / Math.max(1, canvas.clientHeight));
      yaw = -Math.PI / 3;
      elevation = 0.65;
      if (name === "reverse") yaw += Math.PI;
      if (name === "top") { yaw = -Math.PI / 2; elevation = Math.PI / 2 - 0.00001; }
      if (name === "front") { yaw = -Math.PI / 2; elevation = 0; }
      activeView = name;
      draw();
    };
    const zoomBy = factor => {
      zoom = Math.max(0.1, Math.min(20, zoom * factor));
      draw();
    };
    document.querySelectorAll("[data-view]").forEach(button =>
      button.addEventListener("click", () => preset(button.dataset.view))
    );
    document.querySelectorAll("[data-piece]").forEach(checkbox =>
      checkbox.addEventListener("change", () => {
        const index = Number(checkbox.dataset.piece);
        if (checkbox.checked) hidden.delete(index); else hidden.add(index);
        draw();
      })
    );
    document.getElementById("zoom-in").addEventListener("click", () => zoomBy(1.2));
    document.getElementById("zoom-out").addEventListener("click", () => zoomBy(1/1.2));
    document.getElementById("reset").addEventListener("click", () => {
      hidden.clear();
      document.querySelectorAll("[data-piece]").forEach(checkbox => { checkbox.checked = true; });
      preset("iso");
    });
    canvas.addEventListener("wheel", event => {
      event.preventDefault();
      zoomBy(Math.exp(-Math.max(-200, Math.min(200, event.deltaY)) * 0.0015));
    }, {passive: false});
    canvas.addEventListener("contextmenu", event => event.preventDefault());
    let drag;
    canvas.addEventListener("pointerdown", event => {
      canvas.focus();
      canvas.setPointerCapture(event.pointerId);
      drag = {x: event.clientX, y: event.clientY, pan: event.shiftKey || event.button === 2};
    });
    canvas.addEventListener("pointermove", event => {
      if (!drag) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (drag.pan || event.shiftKey) {
        const scale = 2 * radius / zoom / Math.max(1, canvas.clientHeight);
        target = target.map((v, i) => v + scale * (-dx * axes.right[i] + dy * axes.up[i]));
      } else {
        yaw -= dx * 0.008;
        elevation = Math.max(-1.5, Math.min(1.5, elevation + dy * 0.008));
        activeView = "orbit";
      }
      drag.x = event.clientX;
      drag.y = event.clientY;
      draw();
    });
    const stopDrag = () => { drag = null; };
    canvas.addEventListener("pointerup", stopDrag);
    canvas.addEventListener("pointercancel", stopDrag);
    canvas.addEventListener("lostpointercapture", stopDrag);
    canvas.addEventListener("keydown", event => {
      if (event.key.toLowerCase() === "r") { preset("iso"); return; }
      if (event.key === "+" || event.key === "=") { zoomBy(1.2); return; }
      if (event.key === "-") { zoomBy(1/1.2); return; }
      if (!event.key.startsWith("Arrow")) return;
      event.preventDefault();
      if (event.key === "ArrowLeft") yaw -= 0.15;
      if (event.key === "ArrowRight") yaw += 0.15;
      if (event.key === "ArrowUp") elevation = Math.min(1.5, elevation + 0.15);
      if (event.key === "ArrowDown") elevation = Math.max(-1.5, elevation - 0.15);
      activeView = "orbit";
      draw();
    });
    preset("iso");
    new ResizeObserver(draw).observe(canvas);
    const error = gl.getError();
    if (error !== gl.NO_ERROR) throw Error(`WebGL error ${error}`);
  } catch (error) {
    status.textContent = `3D preview unavailable: ${error.message}. Use the geometry images below.`;
    console.error(error);
  }
})();
