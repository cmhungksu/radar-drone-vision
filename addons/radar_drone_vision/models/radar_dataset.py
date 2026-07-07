import json
import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RadarDataset(models.Model):
    _name = 'radar.dataset'
    _description = '雷達資料集'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    name = fields.Char('資料集名稱', required=True, tracking=True)
    dataset_type = fields.Selection([
        ('zenodo77', 'Zenodo 77GHz FMCW'),
        ('synthetic', '合成資料'),
        ('custom', '自訂資料集'),
    ], string='資料集類型', required=True, tracking=True)
    state = fields.Selection([
        ('draft', '草稿'),
        ('downloading', '下載中'),
        ('downloaded', '已下載'),
        ('processing', '處理中'),
        ('ready', '已就緒'),
        ('error', '錯誤'),
    ], string='狀態', default='draft', tracking=True)
    num_samples = fields.Integer('樣本數量', readonly=True)
    num_uav = fields.Integer('UAV 樣本數', readonly=True)
    num_non_uav = fields.Integer('非 UAV 樣本數', readonly=True)
    carrier_freq_hz = fields.Float('載波頻率 (Hz)')
    radar_type = fields.Char('雷達類型')
    doi = fields.Char('DOI')
    notes = fields.Text('備註')
    download_progress = fields.Float('下載進度 (%)', readonly=True)

    def action_download(self):
        """呼叫 AI Worker 下載資料集"""
        self.ensure_one()
        self.state = 'downloading'
        try:
            result = self._call_worker('/datasets/prepare', 'POST', {
                'dataset_type': self.dataset_type,
                'doi': self.doi or '',
            })
            if result:
                self.state = 'downloaded'
                self.message_post(body='資料集下載完成')
        except Exception as e:
            self.state = 'error'
            self.message_post(body=f'下載失敗：{e}')
            raise UserError(f'下載資料集失敗：{e}')

    def action_prepare(self):
        """呼叫 AI Worker 準備資料集（特徵擷取前處理）"""
        self.ensure_one()
        self.state = 'processing'
        try:
            result = self._call_worker('/features/extract', 'POST', {
                'dataset_type': self.dataset_type,
            })
            if result:
                vals = {}
                if result.get('num_samples'):
                    vals['num_samples'] = result['num_samples']
                if result.get('num_uav'):
                    vals['num_uav'] = result['num_uav']
                if result.get('num_non_uav'):
                    vals['num_non_uav'] = result['num_non_uav']
                vals['state'] = 'ready'
                self.write(vals)
                self.message_post(body='資料集準備完成')
        except Exception as e:
            self.state = 'error'
            self.message_post(body=f'準備失敗：{e}')
            raise UserError(f'準備資料集失敗：{e}')

    def action_reset_draft(self):
        """重設為草稿"""
        self.ensure_one()
        self.state = 'draft'

    def action_refresh_stats(self):
        """從 AI Worker 重新取得統計資訊"""
        self.ensure_one()
        try:
            result = self._call_worker('/datasets', 'GET')
            if result and isinstance(result, list):
                for ds in result:
                    ds_type = ds.get('type') or ds.get('dataset_type')
                    if ds_type == self.dataset_type:
                        self.write({
                            'num_samples': ds.get('num_samples', 0),
                            'num_uav': ds.get('num_uav', 0),
                            'num_non_uav': ds.get('num_non_uav', 0),
                        })
                        break
        except Exception as e:
            _logger.warning('取得資料集統計失敗：%s', e)

    def _call_worker(self, endpoint, method='GET', data=None):
        """呼叫 AI Worker API"""
        worker_url = self.env['ir.config_parameter'].sudo().get_param(
            'radar.ai_worker_url', 'http://ai-worker:8000')
        url = f'{worker_url}{endpoint}'
        try:
            if method == 'GET':
                resp = requests.get(url, timeout=30)
            elif method == 'POST':
                resp = requests.post(url, json=data or {}, timeout=120)
            else:
                raise UserError(f'不支援的 HTTP 方法：{method}')
            resp.raise_for_status()
            return resp.json() if resp.text else {}
        except requests.exceptions.ConnectionError:
            raise UserError('無法連線至 AI Worker，請確認服務是否啟動。')
        except requests.exceptions.Timeout:
            raise UserError('AI Worker 回應逾時。')
        except requests.exceptions.HTTPError as e:
            raise UserError(f'AI Worker 回傳錯誤：{e}')
