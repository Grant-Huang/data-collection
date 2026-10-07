// Mic capture on the audio-rendering thread (same processor as web-demo/static/
// mic-capture-worklet.js -- see that file for why an AudioWorklet instead of the deprecated
// ScriptProcessorNode). Posts batches of raw Float32 samples at the AudioContext's native
// rate; resampling to 16 kHz PCM16 happens in useVoiceDictation.ts on the main thread.
const BATCH_SAMPLES = 4096;

class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._batch = new Float32Array(BATCH_SAMPLES);
    this._filled = 0;
  }

  process(inputs) {
    const input = inputs[0][0];
    if (!input) return true;
    let offset = 0;
    while (offset < input.length) {
      const take = Math.min(BATCH_SAMPLES - this._filled, input.length - offset);
      this._batch.set(input.subarray(offset, offset + take), this._filled);
      this._filled += take;
      offset += take;
      if (this._filled === BATCH_SAMPLES) {
        const batch = this._batch;
        this._batch = new Float32Array(BATCH_SAMPLES);
        this._filled = 0;
        this.port.postMessage(batch, [batch.buffer]);
      }
    }
    return true;
  }
}

registerProcessor("mic-capture", MicCaptureProcessor);
