/* 독립 WebGL2 광학/사진 손상 처리. render는 시간만 입력으로 쓰는 순수 함수다. */
(function () {
  'use strict';
  const VERTEX = `#version 300 es
  in vec2 p; out vec2 uv;
  void main(){ uv=p*.5+.5; gl_Position=vec4(p,0.,1.); }`;
  const FRAGMENT = `#version 300 es
  precision highp float;
  in vec2 uv; out vec4 outColor;
  uniform sampler2D image; uniform vec2 size;
  uniform float radius, gain, fringe, tear, band, time;
  float hash(float n){ return fract(sin(n*127.1+311.7)*43758.5453123); }
  float luma(vec3 c){ return dot(c,vec3(.2126,.7152,.0722)); }
  float movingBand(vec2 p){
    float rows=3.+band*10.;
    float y=fract(p.y*rows-time*(.42+band*1.7));
    return smoothstep(.78,.93,y)*(1.-smoothstep(.965,1.,y));
  }
  vec4 damaged(vec2 p){
    float row=floor(p.y*size.y*.5);
    float phase=floor(time*18.);
    float h=hash(row+phase*19.);
    float pulse=movingBand(p);
    float amount=tear*(.18+.82*pulse*band);
    float x=(h-.5)*amount*(9.+23.*band)/size.x;
    float channel=tear*(.25+.75*pulse)*(.35+fringe)*1.5/size.x;
    vec2 q=clamp(p+vec2(x,0.),vec2(0.),vec2(1.));
    vec3 rgb=vec3(
      texture(image,clamp(q+vec2(channel,0.),vec2(0.),vec2(1.))).r,
      texture(image,q).g,
      texture(image,clamp(q-vec2(channel,0.),vec2(0.),vec2(1.))).b);
    vec4 base=texture(image,q);
    float dropout=band*pulse*(.025+.055*hash(row+phase*5.));
    return vec4(rgb*(1.-dropout),base.a);
  }
  void main(){
    vec4 base=damaged(uv);
    if(radius<=0.) { outColor=base; return; }
    vec3 blurredPM=vec3(0.), bloomPM=vec3(0.);
    float sampledAlpha=0.;
    const float COUNT=96.; const float GOLDEN=2.39996323;
    for(int i=0;i<96;i++){
      float f=float(i);
      float disk=sqrt((f+.5)/COUNT);
      float ring=.68+.32*(f+.5)/COUNT;
      float r=mix(disk,ring,fringe);
      vec2 d=vec2(cos(f*GOLDEN),sin(f*GOLDEN))*r*radius/size;
      vec4 s=damaged(clamp(uv+d,vec2(0.),vec2(1.)));
      float bright=smoothstep(.54,.94,luma(s.rgb));
      blurredPM+=s.rgb*s.a;
      bloomPM+=s.rgb*s.a*bright;
      sampledAlpha+=s.a;
    }
    float a=base.a;
    vec3 blurred=blurredPM/max(sampledAlpha,.00001);
    vec3 bloom=bloomPM/max(sampledAlpha,.00001);
    vec3 color=min(blurred+bloom*(gain*.42),vec3(1.));
    outColor=vec4(a>0.?color:vec3(0.),a);
  }`;
  const number = (value, fallback, max) => Math.min(max, Math.max(0, Number.isFinite(Number(value)) ? Number(value) : fallback));

  function compile(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source); gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) || 'ArchiveOptics shader compile failed');
    return shader;
  }

  function create(width = 960, height = 540) {
    width = Math.max(1, Math.round(width)); height = Math.max(1, Math.round(height));
    const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
    const gl = canvas.getContext('webgl2', { preserveDrawingBuffer: true, alpha: true, premultipliedAlpha: false });
    if (!gl) throw new Error('ArchiveOptics requires WebGL2');
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || 'ArchiveOptics shader link failed');
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(program, 'p');
    gl.useProgram(program); gl.enableVertexAttribArray(pos); gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
    const uniform = Object.fromEntries(['image', 'size', 'radius', 'gain', 'fringe', 'tear', 'band', 'time'].map(k => [k, gl.getUniformLocation(program, k)]));
    const texture = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    let sourceWidth = 0, sourceHeight = 0;
    function render(source, options = {}) {
      const sw = source.videoWidth || source.naturalWidth || source.width;
      const sh = source.videoHeight || source.naturalHeight || source.height;
      if (!(sw > 0 && sh > 0)) throw new Error('ArchiveOptics source has no drawable size');
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texture);
      // Canvas 입력은 프레임마다 바뀔 수 있다. 크기만 같으면 저장공간을 재할당하지 않는다.
      if (sw !== sourceWidth || sh !== sourceHeight) { gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source); sourceWidth = sw; sourceHeight = sh; }
      else gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, gl.RGBA, gl.UNSIGNED_BYTE, source);
      const radius = number(options.radius, 0, 80), gain = number(options.gain, 0, 1);
      gl.viewport(0, 0, width, height); gl.useProgram(program);
      gl.uniform1i(uniform.image, 0); gl.uniform2f(uniform.size, width, height);
      gl.uniform1f(uniform.radius, radius); gl.uniform1f(uniform.gain, gain);
      gl.uniform1f(uniform.fringe, number(options.fringe, 0, 1)); gl.uniform1f(uniform.tear, number(options.tear, 0, 1));
      gl.uniform1f(uniform.band, number(options.band, 0, 1)); gl.uniform1f(uniform.time, Number.isFinite(Number(options.time)) ? Number(options.time) : 0);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      return canvas;
    }
    return { canvas, render };
  }
  window.ArchiveOptics = { create };
}());
