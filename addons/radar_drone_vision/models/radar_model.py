import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RadarModel(models.Model):
    _name = 'radar.model'
    _description = '已訓練模型'
    _order = 'create_date desc'

    name = fields.Char('模型名稱', required=True)
    model_type = fields.Selection([
        ('sra', 'SRA (論文演算法)'),
        ('cnn', 'CNN (PyTorch)'),
        ('crnn', 'CRNN'),
        ('transformer', 'Transformer'),
    ], string='模型類型')
    experiment_id = fields.Many2one('radar.experiment', string='來源實驗', readonly=True)
    file_path = fields.Char('檔案路徑')
    eer = fields.Float('EER', digits=(6, 4))
    accuracy = fields.Float('準確率', digits=(6, 4))
    is_active = fields.Boolean('啟用中', default=False)
    notes = fields.Text('備註')

    def action_activate(self):
        """啟用此模型（同時停用其他同類型模型）"""
        self.ensure_one()
        # 停用同類型的其他模型
        same_type = self.search([
            ('model_type', '=', self.model_type),
            ('is_active', '=', True),
            ('id', '!=', self.id),
        ])
        if same_type:
            same_type.write({'is_active': False})
        self.is_active = True

    def action_deactivate(self):
        """停用此模型"""
        self.ensure_one()
        self.is_active = False
