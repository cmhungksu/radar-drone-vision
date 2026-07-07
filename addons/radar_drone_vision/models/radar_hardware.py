import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RadarHardware(models.Model):
    _name = 'radar.hardware'
    _description = '雷達硬體裝置'
    _order = 'name'

    name = fields.Char('裝置名稱', required=True)
    device_type = fields.Selection([
        ('simulator', '模擬器'),
        ('generic_iq', 'Generic I/Q'),
        ('ti_mmwave', 'TI mmWave'),
        ('infineon', 'Infineon'),
    ], string='裝置類型', required=True)
    state = fields.Selection([
        ('disconnected', '已斷線'),
        ('connected', '已連線'),
        ('error', '錯誤'),
    ], string='連線狀態', default='disconnected')
    host = fields.Char('主機位址', default='localhost')
    port = fields.Integer('連接埠', default=5555)
    frames_received = fields.Integer('已接收幀數', readonly=True)
    latency_ms = fields.Float('平均延遲 (ms)', readonly=True)
    notes = fields.Text('備註')

    def action_connect(self):
        """連線至硬體裝置"""
        self.ensure_one()
        try:
            result = self._call_worker('/hardware/connect', 'POST', {
                'device_type': self.device_type,
                'host': self.host or 'localhost',
                'port': self.port or 5555,
            })
            if result:
                self.state = 'connected'
        except Exception as e:
            self.state = 'error'
            raise UserError(f'連線失敗：{e}')

    def action_disconnect(self):
        """斷線"""
        self.ensure_one()
        try:
            self._call_worker('/hardware/disconnect', 'POST', {
                'device_type': self.device_type,
            })
        except Exception:
            pass
        self.state = 'disconnected'

    def action_refresh_status(self):
        """重新取得硬體狀態"""
        self.ensure_one()
        try:
            result = self._call_worker('/hardware/status', 'GET')
            if result:
                vals = {}
                state = result.get('state') or result.get('status')
                if state == 'connected':
                    vals['state'] = 'connected'
                elif state in ('disconnected', 'offline'):
                    vals['state'] = 'disconnected'
                if result.get('frames_received') is not None:
                    vals['frames_received'] = result['frames_received']
                if result.get('latency_ms') is not None:
                    vals['latency_ms'] = result['latency_ms']
                if vals:
                    self.write(vals)
        except Exception as e:
            _logger.warning('取得硬體狀態失敗：%s', e)

    def _call_worker(self, endpoint, method='GET', data=None):
        """呼叫 AI Worker API"""
        worker_url = self.env['ir.config_parameter'].sudo().get_param(
            'radar.ai_worker_url', 'http://ai-worker:8000')
        url = f'{worker_url}{endpoint}'
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=15)
            elif method == 'POST':
                resp = requests.post(url, json=data or {}, timeout=30)
            else:
                raise UserError(f'不支援的 HTTP 方法：{method}')
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except requests.exceptions.ConnectionError:
            raise UserError('無法連線至 AI Worker。')
        except requests.exceptions.Timeout:
            raise UserError('AI Worker 回應逾時。')
        except requests.exceptions.HTTPError as e:
            raise UserError(f'AI Worker 回傳錯誤：{e}')
