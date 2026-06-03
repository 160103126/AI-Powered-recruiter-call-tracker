import os
try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None


def _load_whisper_model(size='small'):
    if WhisperModel is None:
        raise RuntimeError('faster-whisper not installed')
    # Try compute types in order of efficiency -> compatibility
    compute_attempts = ['int8_float16', 'int8', None]
    last_exc = None
    for compute in compute_attempts:
        try:
            if compute:
                model = WhisperModel(size, device='cpu', compute_type=compute)
            else:
                model = WhisperModel(size, device='cpu')
            return model, compute
        except Exception as e:
            last_exc = e
            continue
    # If all attempts failed, raise last exception
    raise last_exc


def transcribe_file(path, lang=None, model_size='small'):
    # Load model (with fallback compute types)
    model, used_compute = _load_whisper_model(model_size)
    segments, info = model.transcribe(path, beam_size=5, language=lang)
    text = ' '.join([s.text for s in segments])
    return {'transcript': text, 'model': model_size, 'compute_type': used_compute, 'duration': info.duration}
