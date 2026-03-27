import os
import sys
import traceback

try:
    from dotenv import load_dotenv
    from flask import Flask, jsonify, render_template, request
    from db import get_db
    load_dotenv('.env.esop')
    _BOOT_ERROR = None
except Exception as _e:
    _BOOT_ERROR = traceback.format_exc()
    from flask import Flask, jsonify
    def get_db(): raise RuntimeError('DB not available')
    def render_template(*a, **kw): return f'<pre>Boot error:\n{_BOOT_ERROR}</pre>'
    class _R:
        path = ''
        method = ''
        endpoint = ''
        headers = {}
        remote_addr = ''
    request = _R()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'esop-dev-key-change-in-prod')

if _BOOT_ERROR:
    @app.route('/')
    @app.route('/<path:p>')
    def boot_error(p=''):
        return f'<pre style="background:#0d1117;color:#ef4444;padding:20px;font-family:monospace">ESOP Boot Error:\n\n{_BOOT_ERROR}</pre>', 500

@app.before_request
def check_api_key():
    api_key = os.environ.get('ESOP_API_KEY')
    if api_key and request.path.startswith('/api/'):
        provided = request.headers.get('X-API-Key', '')
        if provided != api_key:
            return {'error': 'Unauthorized'}, 401

@app.errorhandler(Exception)
def handle_global_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    error_msg = str(e)
    tb = traceback.format_exc()
    print(f"Error: {error_msg}\n{tb}", file=sys.stderr)
    if request.path.startswith('/api/'):
        return jsonify({'error': error_msg}), 500
    return f'<pre style="background:#0d1117;color:#ef4444;padding:20px;font-family:monospace">{error_msg}\n\n{tb}</pre>', 500

bluprints_dir = os.path.join(os.path.dirname(__file__), 'blueprints')
sys.path.insert(0, os.path.dirname(__file__))

_bp_errors = []
if not _BOOT_ERROR:
    import importlib.util
    for filename in sorted(os.listdir(blueprints_dir)):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(
                    module_name, os.path.join(blueprints_dir, filename)
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                if hasattr(module, 'bp'):
                    app.register_blueprint(module.bp)
            except Exception as e:
                _bp_errors.append(f'{filename}: {e}')

@app.route('/')
def index():
    return render_template('landing.html')

@app.route('/app/')
def shell():
    return render_template('shell.html')

@app.route('/api/debug')
def debug_info():
    return jsonify({
        'boot_error': _BOOT_ERROR,
        'blueprint_errors': _bp_errors,
        'python': sys.version,
        'app': 'ESOP'
    })

@app.route('/api/health')
def health_check():
    result = {'status': 'ok', 'app': 'ESOP', 'python': sys.version}
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1 as ok')
        cur.fetchone()
        cur.close()
        conn.close()
        result['db'] = 'connected'
    except Exception as e:
        result['db'] = f'error: {e}'
        result['status'] = 'db_error'
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5011, debug=os.environ.get('FLASK_DEBUG', '0') == '1', use_reloader=False)
