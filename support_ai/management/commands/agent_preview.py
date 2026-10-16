"""Chat with the current Agent from a console, without HTTP or a browser."""
import json
import sys

from django.core.management.base import BaseCommand, CommandError

from support_ai.preview import PreviewSession
from users.models import UserProfile


HELP = ('直接输入问题并回车。 /new 新对话；/history 当前上下文；/plan 上轮计划；'
        '/rag 上轮查询与补检；/config 当前配置；/help 帮助；/exit 退出。')


class Command(BaseCommand):
    help = '终端 Agent 预览：真实模型、商品、RAG 和多轮上下文，无需网页或 HTTP 服务。'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--message', action='append', help='单次输入；可重复传入，按同一会话顺序执行。')
        parser.add_argument('--user-id', type=int, help='明确指定活跃买家，启用其偏好、私有知识和订单上下文。')
        parser.add_argument('--log-dir', help='脱敏 JSONL 记录目录，默认 reports/agent-preview。')
        parser.add_argument('--telemetry', action='store_true', help='按运营配置写入并导出 OTel 监控；默认关闭以隔离预览。')
        parser.add_argument('--json', action='store_true', help='配合 --message，输出完整 JSONL 结果。')

    def handle(self, *args, **options):
        if options['json'] and not options['message']:
            raise CommandError('--json 需要配合 --message。')
        if options['message'] and any(not m.strip() or len(m) > 1000 for m in options['message']):
            raise CommandError('请输入 1 至 1000 字的问题。')
        try:
            user = None
            if options['user_id'] is not None:
                user = UserProfile.objects.filter(pk=options['user_id'], is_active=True, user_type='customer').first()
                if user is None:
                    raise CommandError('--user-id 必须是已激活的买家账号 ID。')
            session = PreviewSession(user=user, log_dir=options['log_dir'], telemetry=options['telemetry'])
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError('预览初始化失败（{}），请检查数据库和模型配置。'.format(type(exc).__name__)) from None
        if options['message']:
            for message in options['message']:
                try:
                    self.show(session.ask(message), options['json'])
                except Exception as exc:
                    raise CommandError(self.error_hint(session, exc)) from None
            if not options['json']:
                self.stdout.write('记录：' + str(session.log_path))
            return
        self.stdout.write(self.style.SUCCESS('Dadashop Agent 终端预览已就绪'))
        self.stdout.write(json.dumps(session.status(), ensure_ascii=False, indent=2))
        self.stdout.write('输入会调用当前模型服务；记录经现有规则脱敏后保存在本地。\n' + HELP)
        while True:
            try:
                self.stdout.write('\n你 > ', ending='')
                self.stdout.flush()
                line = sys.stdin.readline()
                if not line:
                    break
                message = line.strip()
                if not message:
                    continue
                if message.lower() in ('/exit', '/quit'):
                    break
                if message == '/help':
                    self.stdout.write(HELP)
                elif message == '/new':
                    session.new()
                    self.stdout.write('已开始新对话。记录：' + str(session.log_path))
                elif message == '/config':
                    self.stdout.write(json.dumps(session.status(), ensure_ascii=False, indent=2))
                elif message == '/history':
                    self.stdout.write(json.dumps(session.history(), ensure_ascii=False, indent=2))
                elif message == '/plan':
                    plan = (session.last_error or {}).get('task_plan') or (
                        session.last_record['response']['task_plan'] if session.last_record else {})
                    self.stdout.write(json.dumps(plan, ensure_ascii=False, indent=2))
                elif message == '/rag':
                    record = session.last_error or session.last_record or {}
                    self.stdout.write(json.dumps(record.get('retrieval', []), ensure_ascii=False, indent=2))
                elif message.startswith('/'):
                    self.stdout.write('未知命令。' + HELP)
                elif len(message) > 1000:
                    self.stdout.write('请输入 1 至 1000 字的问题。')
                else:
                    self.stdout.write('Agent 正在处理…')
                    self.stdout.flush()
                    self.show(session.ask(message))
            except (EOFError, KeyboardInterrupt):
                break
            except Exception as exc:
                self.stderr.write(self.error_hint(session, exc) + '\n可以继续输入或 /new。')
        self.stdout.write('\n预览已结束。记录：' + str(session.log_path))

    def error_hint(self, session, exc):
        tasks = (session.last_error or {}).get('tasks', [])
        details = '；'.join('{}: {}'.format(t['tool'], t['error_type'] or t['status']) for t in tasks)
        diagnostic = [d for t in tasks for d in t.get('diagnostics', [])]
        if diagnostic:
            details += '；' + json.dumps(diagnostic, ensure_ascii=False)
        return '本轮失败（{}）{}。记录：{}'.format(type(exc).__name__, '；' + details if details else '', session.log_path)

    def show(self, record, as_json=False):
        if as_json:
            self.stdout.write(json.dumps(record, ensure_ascii=False))
            return
        response = record['response']
        self.stdout.write('\nAgent > ' + response['answer'])
        self.stdout.write('\n[分析] 意图：{}；来源：{}；上下文：{} 轮；耗时：{}s'.format(
            ' → '.join(response['intents']), response['intent_source'], record['context_turns'], record['elapsed_seconds']))
        self.stdout.write('[任务] ' + ' → '.join('{} ({})'.format(t['tool'], t['status']) for t in response['tasks']))
        if record.get('compliance_blocked'):
            self.stdout.write('[合规] 当前 Agent 拦截了生成回复，已返回安全兜底内容。')
        for diagnostic in response.get('diagnostics', []):
            self.stdout.write('[诊断] ' + json.dumps(diagnostic, ensure_ascii=False))
        self.stdout.write('[模型] {}；调用 {} 次；Token 输入 {} / 输出 {}'.format(
            record['model'], record['model_calls'], record['input_tokens'], record['output_tokens']))
        retrieval = record.get('retrieval', [])
        if retrieval:
            self.stdout.write('[检索] {} 项；查询 {} 次；补检 {} 项；/rag 查看详情'.format(
                len(retrieval), sum(len(r['queries']) for r in retrieval), sum(r['retry'] for r in retrieval)))
