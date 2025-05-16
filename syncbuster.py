import sys
import json
import threading
import time
import re
import warnings
import requests
from urllib.parse import urlparse
import traceback
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                           QHBoxLayout, QTextEdit, QPushButton, QLabel,
                           QTabWidget, QSplitter, QComboBox, QCheckBox, QLineEdit,
                           QGroupBox, QRadioButton, QButtonGroup, QMenu)
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread, QEvent
from PySide6.QtGui import QFont, QPalette, QColor, QTextCursor, QAction

warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

class SignalManager(QObject):
    log_signal = Signal(str, str)
    result_ready_signal = Signal(object)  # 用于请求结果

signal_manager = SignalManager()

class RequestTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # 数据包输入
        self.request_input = QTextEdit()
        self.request_input.setPlaceholderText("请输入完整HTTP数据包，格式如下：\n\nPOST /api/data HTTP/1.1\nHost: example.com\nContent-Type: application/json\n\n{\"key\": \"value\"}")
        
        settings_group = QGroupBox("请求设置")
        settings_layout = QHBoxLayout()
        
        # 延迟设置
        delay_layout = QHBoxLayout()
        self.delay_checkbox = QCheckBox("请求延迟")
        self.delay_input = QLineEdit()
        self.delay_input.setPlaceholderText("延迟秒数")
        self.delay_input.setMaximumWidth(100)
        delay_layout.addWidget(self.delay_checkbox)
        delay_layout.addWidget(self.delay_input)
        
        # 协议选择（默认http）
        self.https_checkbox = QCheckBox("强制HTTPS")
        self.https_checkbox.setToolTip("选中时强制使用HTTPS协议，未选中时强制使用HTTP协议")
        
        # 添加到设置组
        settings_layout.addLayout(delay_layout)
        settings_layout.addWidget(self.https_checkbox)
        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        
        # 并发功能区域ui
        layout.addWidget(QLabel("HTTP数据包:"))
        layout.addWidget(self.request_input)
        layout.addWidget(settings_group)
        
        self.setLayout(layout)
        
    def get_delay(self):
        """获取设置的延迟时间（秒）"""
        if not self.delay_checkbox.isChecked():
            return 0
            
        try:
            return float(self.delay_input.text())
        except (ValueError, TypeError):
            return 0
            
    def get_protocol(self):
        """获取选择的协议"""
        return "https" if self.https_checkbox.isChecked() else "http"

class FollowupRequestTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(8)  # 减少各组件之间的垂直间距
        
        # 后续请求设置
        settings_group = QGroupBox("后续请求设置")
        settings_layout = QHBoxLayout()
        settings_layout.setContentsMargins(8, 6, 8, 6)  # 减少内边距
        
        # 是否启用后续请求
        self.enable_checkbox = QCheckBox("启用后续请求")
        
        # 协议选择 - 与主请求一致使用复选框
        self.https_checkbox = QCheckBox("强制HTTPS")
        self.https_checkbox.setToolTip("选中时强制使用HTTPS协议，未选中时强制使用HTTP协议")
        
        # 数据源选择
        source_label = QLabel("数据源:")
        self.source_group = QButtonGroup()
        self.source_req1 = QRadioButton("请求1")
        self.source_req2 = QRadioButton("请求2")
        self.source_group.addButton(self.source_req1, 1)
        self.source_group.addButton(self.source_req2, 2)
        self.source_req1.setChecked(True)
        
        # 添加到设置布局
        settings_layout.addWidget(self.enable_checkbox)
        settings_layout.addWidget(self.https_checkbox)
        settings_layout.addSpacing(20)  # 添加一些间距
        settings_layout.addWidget(source_label)
        settings_layout.addWidget(self.source_req1)
        settings_layout.addWidget(self.source_req2)
        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        
        # 正则表达式提取部分
        regex_group = QGroupBox("正则表达式提取")
        regex_layout = QVBoxLayout()
        regex_layout.setContentsMargins(8, 6, 8, 6)  # 减少内边距
        regex_layout.setSpacing(5)  # 减少垂直间距
        
        # 创建后续请求功能中re匹配的提示文本
        regex_help_layout = QVBoxLayout()
        regex_help_layout.setSpacing(2)
        regex_help_left = QLabel("① 提取正则: 从选定数据源(请求1或2)的响应中提取值")
        regex_help_right = QLabel("② 结果正则: 从后续请求的响应结果中提取最终数据")
        regex_help_layout.addWidget(regex_help_left)
        regex_help_layout.addWidget(regex_help_right)
        
        # 提取的正则表达式
        regex_input_layout = QHBoxLayout()
        regex_input_layout.addWidget(QLabel("① 提取正则:"))
        self.regex_input = QLineEdit()
        self.regex_input.setText("\"result\":\\s*\"([^\"]+)\"")
        self.regex_input.setPlaceholderText("输入正则表达式，从数据源响应中提取值")
        self.regex_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.regex_input.customContextMenuRequested.connect(self.show_regex_context_menu)
        regex_input_layout.addWidget(self.regex_input)
        
        # 结果提取的正则表达式
        result_regex_layout = QHBoxLayout()
        result_regex_layout.addWidget(QLabel("② 结果正则:"))
        self.result_regex_input = QLineEdit()
        self.result_regex_input.setText("\"result\":\\s*\"([^\"]+)\"")
        self.result_regex_input.setPlaceholderText("输入正则表达式，从后续请求结果中提取数据")
        self.result_regex_input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.result_regex_input.customContextMenuRequested.connect(self.show_result_regex_context_menu)
        result_regex_layout.addWidget(self.result_regex_input)
        
        # 添加到正则布局
        regex_layout.addLayout(regex_help_layout)
        regex_layout.addLayout(regex_input_layout)
        regex_layout.addLayout(result_regex_layout)
        regex_group.setLayout(regex_layout)
        
        # 完整数据包输入
        request_group = QGroupBox("后续请求数据包")
        request_layout = QVBoxLayout()
        request_layout.setContentsMargins(8, 6, 8, 6)  # 减少内边距
        
        # 添加说明标签
        instruction_label = QLabel("在下面输入HTTP请求数据包，使用 {{regex_result}} 引用第①步提取的值")
        instruction_label.setWordWrap(True)
        request_layout.addWidget(instruction_label)
        
        self.request_input = QTextEdit()
        self.request_input.setPlaceholderText("POST /api/verify HTTP/1.1\nHost: example.com\nContent-Type: application/json\n\n{\"token\": \"{{regex_result}}\"}")
        request_layout.addWidget(self.request_input)
        request_group.setLayout(request_layout)
        
        # 添加所有组件
        layout.addWidget(settings_group)
        layout.addWidget(regex_group)
        layout.addWidget(request_group, 1)  # 给请求数据包更多空间
        
        self.setLayout(layout)
    
    def show_regex_context_menu(self, pos):
        """显示正则表达式输入框的自定义右键菜单"""
        menu = QMenu(self)
        
        # 添加转换为非贪婪匹配选项
        convert_action = QAction("转换为非贪婪匹配 (将 .* 替换为 .*?)", self)
        convert_action.triggered.connect(self.convert_to_non_greedy)
        menu.addAction(convert_action)
        
        # 添加示例选项（右键即可快捷使用）
        examples_menu = QMenu("正则表达式示例", self)
        
        json_example1 = QAction("JSON字段（可能会多匹配，或匹配不到）: \"name\":\"(.*?)\"", self)
        json_example1.triggered.connect(lambda: self.insert_regex_example("\"name\":\"(.*?)\""))
        
        json_example2 = QAction("单JSON字段（推荐）: \"result\"\\s*:*\"([^\"]+)\"", self)
        json_example2.triggered.connect(lambda: self.insert_regex_example("\"key\"\\s*:\\s*\"([^\"]+)\""))
        
        json_example3 = QAction("指定上下文: \"prefix\":\"(.*?)\",\"suffix\"", self)
        json_example3.triggered.connect(lambda: self.insert_regex_example("\"prefix\":\"(.*?)\",\"suffix\""))
        
        json_example4 = QAction("数字值: \"id\"\\s*:\\s*(\\d+)", self)
        json_example4.triggered.connect(lambda: self.insert_regex_example("\"id\"\\s*:\\s*(\\d+)"))
        
        json_example5 = QAction("嵌套JSON: \\{\"data\":\\{\"key\":\"(.*?)\"\\}\\}", self)
        json_example5.triggered.connect(lambda: self.insert_regex_example("\\{\"data\":\\{\"key\":\"(.*?)\"\\}\\}"))
        
        examples_menu.addAction(json_example1)
        examples_menu.addAction(json_example2)
        examples_menu.addAction(json_example3)
        examples_menu.addAction(json_example4)
        examples_menu.addAction(json_example5)
        
        menu.addMenu(examples_menu)
        
        # 显示菜单
        menu.exec(self.regex_input.mapToGlobal(pos))
    
    def show_result_regex_context_menu(self, pos):
        """显示结果正则表达式输入框的自定义右键菜单"""
        menu = QMenu(self)
        
        # 添加转换为非贪婪匹配选项
        convert_action = QAction("转换为非贪婪匹配 (将 .* 替换为 .*?)", self)
        convert_action.triggered.connect(self.convert_result_to_non_greedy)
        menu.addAction(convert_action)
        
        # 添加示例选项
        examples_menu = QMenu("正则表达式示例", self)
        
        json_example1 = QAction("JSON字段（可能会多匹配，或匹配不到）: \"name\":\"(.*?)\"", self)
        json_example1.triggered.connect(lambda: self.insert_result_regex_example("\"name\":\"(.*?)\""))
        
        json_example2 = QAction("单JSON字段（推荐）: \"result\"\\s*:*\"([^\"]+)\"", self)
        json_example2.triggered.connect(lambda: self.insert_result_regex_example("\"key\"\\s*:\\s*\"([^\"]+)\""))
        
        json_example3 = QAction("指定上下文: \"prefix\":\"(.*?)\",\"suffix\"", self)
        json_example3.triggered.connect(lambda: self.insert_result_regex_example("\"prefix\":\"(.*?)\",\"suffix\""))
        
        json_example4 = QAction("数字值: \"id\"\\s*:\\s*(\\d+)", self)
        json_example4.triggered.connect(lambda: self.insert_result_regex_example("\"id\"\\s*:\\s*(\\d+)"))
        
        json_example5 = QAction("嵌套JSON: \\{\"data\":\\{\"key\":\"(.*?)\"\\}\\}", self)
        json_example5.triggered.connect(lambda: self.insert_result_regex_example("\\{\"data\":\\{\"key\":\"(.*?)\"\\}\\}"))
        
        examples_menu.addAction(json_example1)
        examples_menu.addAction(json_example2)
        examples_menu.addAction(json_example3)
        examples_menu.addAction(json_example4)
        examples_menu.addAction(json_example5)
        
        menu.addMenu(examples_menu)
        
        # 显示菜单
        menu.exec(self.result_regex_input.mapToGlobal(pos))
    
    def convert_to_non_greedy(self):
        """将贪婪匹配转换为非贪婪匹配"""
        current_text = self.regex_input.text()
        if '.*' in current_text and '.*?' not in current_text:
            new_text = current_text.replace('.*', '.*?')
            self.regex_input.setText(new_text)
            
    def convert_result_to_non_greedy(self):
        """将结果正则表达式的贪婪匹配转换为非贪婪匹配"""
        current_text = self.result_regex_input.text()
        if '.*' in current_text and '.*?' not in current_text:
            new_text = current_text.replace('.*', '.*?')
            self.result_regex_input.setText(new_text)
            
    def insert_regex_example(self, example):
        """插入正则表达式示例"""
        self.regex_input.setText(example)
        
    def insert_result_regex_example(self, example):
        """插入结果正则表达式示例"""
        self.result_regex_input.setText(example)
    
    def is_enabled(self):
        return self.enable_checkbox.isChecked()
    
    def get_source(self):
        id = self.source_group.checkedId()
        if id == 1:
            return "request1"
        else:
            return "request2"
    
    def get_regex(self):
        return self.regex_input.text()
    
    def get_result_regex(self):
        return self.result_regex_input.text()
    
    def get_request_template(self):
        return self.request_input.toPlainText()
        
    def get_protocol(self):
        """获取选择的协议"""
        return "https" if self.https_checkbox.isChecked() else "http"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.setup_signal_connections()
        
        # 调试模式默认关闭
        self.debug_mode = False
        
    def setup_signal_connections(self):
        # 连接日志信号到处理函数
        signal_manager.log_signal.connect(self.on_log_message)
        
    def on_log_message(self, message, target):
        """处理日志消息"""
        # 如果不是调试模式，只过滤掉过程性日志，确保显示结果内容
        if not self.debug_mode:
            # 检查是否是过程性日志
            if not any(keyword in message for keyword in [
                "状态码:", "响应:", "body", "请求体", "⚠️", "❌", "✅",
                "匹配结果", "匹配内容", "响应内容", "=====", "-----",
                "使用第一个匹配值:"
            ]):
                return
            
        if target == "main":
            self.response_text.append(message)
            # 滚动到底部
            self.response_text.moveCursor(QTextCursor.End)
        elif target == "followup":
            self.followup_response_text.append(message)
            # 滚动到底部
            self.followup_response_text.moveCursor(QTextCursor.End)
        
    def toggle_debug_mode(self):
        """切换调试模式"""
        self.debug_mode = not self.debug_mode
        self.debug_button.setText("调试模式: " + ("开启" if self.debug_mode else "关闭"))
        
        if self.debug_mode:
            signal_manager.log_signal.emit("调试模式已开启 - 将显示详细请求信息", "main")
        else:
            signal_manager.log_signal.emit("调试模式已关闭 - 只显示关键信息和响应结果", "main")
        
    def init_ui(self):
        self.setWindowTitle('SyncBuster')
        self.setMinimumSize(1000, 900)  # 增大默认窗口大小
        
        # 设置主窗口样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f0f0f0;
            }
            QLabel {
                font-size: 13px;
                color: #2c3e50;
                line-height: 1.4;
            }
            QTextEdit {
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                padding: 5px;
                background-color: white;
                font-family: "Consolas", monospace;
                font-size: 12px;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 15px;
                border-radius: 3px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QCheckBox {
                spacing: 5px;
                font-size: 13px;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                font-size: 12px;
            }
            QGroupBox {
                border: 1px solid #bdc3c7;
                border-radius: 3px;
                margin-top: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px;
            }
            QRadioButton {
                font-size: 13px;
            }
        """)

        # 创建中央部件
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # 创建上下分隔器
        main_splitter = QSplitter(Qt.Vertical)
        
        # 上部分 - 主要请求区域
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        
        # 水平分隔 - 主请求区域
        request_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧请求面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        self.tab1 = RequestTab()
        self.tab2 = RequestTab()
        self.tab_widget.addTab(self.tab1, "请求 1")
        self.tab_widget.addTab(self.tab2, "请求 2")
        
        left_layout.addWidget(self.tab_widget)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 发送按钮
        self.send_button = QPushButton("发送并发请求")
        self.send_button.clicked.connect(self.on_send_requests)
        
        # 调试模式按钮
        self.debug_button = QPushButton("调试模式: 关闭")
        self.debug_button.clicked.connect(self.toggle_debug_mode)
        
        button_layout.addWidget(self.send_button)
        button_layout.addWidget(self.debug_button)
        
        left_layout.addLayout(button_layout)
        
        # 右侧响应面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setPlaceholderText("响应结果将在这里显示")
        right_layout.addWidget(QLabel("并发请求响应结果:"))
        right_layout.addWidget(self.response_text)
        
        # 添加面板到分割器
        request_splitter.addWidget(left_panel)
        request_splitter.addWidget(right_panel)
        request_splitter.setSizes([500, 500])  # 调整分割比例，左侧更宽
        
        top_layout.addWidget(request_splitter)
        
        # 下部分 - 后续请求区域
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        
        # 水平分隔 - 后续请求区域
        followup_splitter = QSplitter(Qt.Horizontal)
        
        # 左侧后续请求配置
        followup_panel = QWidget()
        followup_layout = QVBoxLayout(followup_panel)
        
        self.followup_tab = FollowupRequestTab()
        followup_layout.addWidget(self.followup_tab)
        
        # 右侧后续响应面板
        followup_response_panel = QWidget()
        followup_response_layout = QVBoxLayout(followup_response_panel)
        
        self.followup_response_text = QTextEdit()
        self.followup_response_text.setReadOnly(True)
        self.followup_response_text.setPlaceholderText("后续请求的响应结果将在这里显示")
        followup_response_layout.addWidget(QLabel("后续请求响应结果:"))
        followup_response_layout.addWidget(self.followup_response_text)
        
        # 添加到分割器
        followup_splitter.addWidget(followup_panel)
        followup_splitter.addWidget(followup_response_panel)
        followup_splitter.setSizes([500, 500])  # 调整分割比例，左侧更宽
        
        bottom_layout.addWidget(followup_splitter)
        
        # 添加到主分割器
        main_splitter.addWidget(top_widget)
        main_splitter.addWidget(bottom_widget)
        main_splitter.setSizes([500, 400])
        
        main_layout.addWidget(main_splitter)
        self.setCentralWidget(central_widget)

    def parse_http_request(self, raw_request, force_protocol=None):
        """解析HTTP原始请求"""
        try:
            # 分离请求头和请求体
            parts = raw_request.split('\n\n', 1)
            headers_block = parts[0]
            body = parts[1] if len(parts) > 1 else ''
            
            # 解析请求行
            header_lines = headers_block.split('\n')
            request_line = header_lines[0]
            request_parts = request_line.split(' ')
            
            if len(request_parts) < 2:
                return {'error': '请求行格式错误，无法解析方法和路径'}
                
            method = request_parts[0]
            path = request_parts[1]
            
            # 解析请求头
            headers = {}
            cookie_found = False  # 用于跟踪是否找到Cookie头
            
            for line in header_lines[1:]:
                line = line.strip()
                if line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        key, value = parts
                        key = key.strip()
                        value = value.strip()
                        headers[key] = value
                        
                        # 标记是否找到Cookie头
                        if key.lower() == 'cookie':
                            cookie_found = True
            
            # 如果没有找到Cookie头，发出警告
            if not cookie_found and self.debug_mode:
                signal_manager.log_signal.emit("警告: 未在请求中找到Cookie头", "main")
            
            # 提取主机信息
            host = headers.get('Host', '')
            if not host:
                return {'error': '缺少Host头，无法构建完整URL'}
            
            # 构建完整URL
            scheme = "auto"
            if force_protocol:
                scheme = force_protocol
            else:
                # 自动检测协议
                scheme = 'https' if 'https' in headers.get('Host', '').lower() else 'http'
            
            # 根据scheme构建URL
            if scheme == "auto":
                scheme = 'https' if 'https' in headers.get('Host', '').lower() else 'http'
            
            url = f"{scheme}://{host}{path}"
            
            return {
                'method': method,
                'url': url,
                'headers': headers,
                'body': body.strip(),
                'raw_request': raw_request,  # 保存原始请求，用于直接发送
                'has_cookie': cookie_found,   # 标记是否有Cookie
                'protocol': scheme  # 记录使用的协议
            }
        except Exception as e:
            signal_manager.log_signal.emit(f"解析HTTP请求失败: {str(e)}", "main")
            return {
                'error': f"解析HTTP请求失败: {str(e)}"
            }

    def send_request_with_requests(self, method, url, headers, body, cookies=None):
        """使用requests库发送HTTP请求"""
        try:
            # 确保方法名是大写的
            method = method.upper()
            
            # 记录方法类型，特别关注POST
            if method == "POST":
                signal_manager.log_signal.emit("⚠️ 检测到POST请求 - 确保以POST方法发送", "main")
            
            # 准备请求参数
            request_kwargs = {
                'headers': headers.copy(),  # 创建副本以防修改
                'verify': False,  # 禁用SSL验证
                'timeout': 30     # 设置超时时间
            }
            
            # 移除Accept-Encoding头，避免响应乱码，这玩意留着请求的内容会压缩，requests解不了
            request_kwargs['headers'].pop('Accept-Encoding', None)
            
            # 添加cookie（如果有）
            if cookies:
                request_kwargs['cookies'] = cookies
            
            # 根据Content-Type处理请求体
            content_type = headers.get('Content-Type', '').lower()
            
            if body:
                if 'application/json' in content_type:
                    try:
                        json_body = json.loads(body)
                        request_kwargs['json'] = json_body
                        if self.debug_mode:
                            signal_manager.log_signal.emit(f"请求体作为JSON发送: {json.dumps(json_body)[:200]}{'...' if len(json.dumps(json_body)) > 200 else ''}", "main")
                    except json.JSONDecodeError as e:
                        request_kwargs['data'] = body
                        if self.debug_mode:
                            signal_manager.log_signal.emit(f"JSON解析失败，请求体作为原始文本发送: {str(e)}", "main")
                else:
                    request_kwargs['data'] = body
                    if self.debug_mode:
                        signal_manager.log_signal.emit(f"请求体作为原始数据发送，Content-Type: {content_type}", "main")
            elif method == "POST" and self.debug_mode:
                signal_manager.log_signal.emit("⚠️ 警告: POST请求没有请求体！", "main")
            
            if self.debug_mode:
                signal_manager.log_signal.emit(f"最终请求方法: {method}", "main")
                signal_manager.log_signal.emit(f"完整请求确认:", "main")
                signal_manager.log_signal.emit(f"  方法: {method}", "main")
                signal_manager.log_signal.emit(f"  URL: {url}", "main")
                signal_manager.log_signal.emit(f"  请求头数量: {len(headers)}", "main")
                signal_manager.log_signal.emit(f"  请求体类型: {'JSON' if 'json' in request_kwargs else '原始数据' if 'data' in request_kwargs else '无'}", "main")
                
                # 输出所有请求头
                for header_name, header_value in headers.items():
                    signal_manager.log_signal.emit(f"  发送头: {header_name}: {header_value[:50]}{'...' if len(header_value) > 50 else ''}", "main")
            
            # 开始计时
            start_time = time.time()
            
            # 使用requests的对应方法发送请求
            signal_manager.log_signal.emit(f"正在使用requests发送{method}请求...", "main")
            
            if method == 'GET':
                response = requests.get(url, **request_kwargs)
            elif method == 'POST':
                response = requests.post(url, **request_kwargs)
            elif method == 'PUT':
                response = requests.put(url, **request_kwargs)
            elif method == 'DELETE':
                response = requests.delete(url, **request_kwargs)
            elif method == 'PATCH':
                response = requests.patch(url, **request_kwargs)
            elif method == 'HEAD':
                response = requests.head(url, **request_kwargs)
            elif method == 'OPTIONS':
                response = requests.options(url, **request_kwargs)
            else:
                # 对于其他方法，使用通用方法
                response = requests.request(method, url, **request_kwargs)
            
            # 计算请求时间
            end_time = time.time()
            time_taken = f"{(end_time - start_time) * 1000:.2f}ms"
            
            # 记录响应状态
            status = response.status_code
            signal_manager.log_signal.emit(f"响应状态码: {status}, 耗时: {time_taken}", "main")
            
            # 检查是否是错误状态码
            if status >= 400:
                signal_manager.log_signal.emit(f"⚠️ 错误响应 {status}! 响应内容:", "main")
                signal_manager.log_signal.emit(response.text[:500] + ('...' if len(response.text) > 500 else ''), "main")
            
            # 检查Set-Cookie头
            if 'Set-Cookie' in response.headers and self.debug_mode:
                signal_manager.log_signal.emit(f"收到Set-Cookie头", "main")
                for cookie in response.cookies:
                    signal_manager.log_signal.emit(f"  Cookie: {cookie.name}={cookie.value}", "main")
            
            # 处理响应编码
            # 首先尝试从Content-Type头获取编码
            content_type = response.headers.get('Content-Type', '').lower()
            encoding = None
            
            if 'charset=' in content_type:
                encoding = content_type.split('charset=')[-1].strip()
            
            # 如果没有在Content-Type中找到编码，尝试使用apparent_encoding
            if not encoding:
                encoding = response.apparent_encoding
            
            # 如果还是没有找到编码，使用常见的编码尝试
            if not encoding or encoding.lower() in ['ascii', 'iso-8859-1']:
                encodings_to_try = ['utf-8', 'gbk', 'gb2312', 'gb18030']
                response_content = response.content
                for enc in encodings_to_try:
                    try:
                        decoded_text = response_content.decode(enc)
                        encoding = enc
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    # 如果所有编码都失败，使用默认的response.text
                    decoded_text = response.text
            else:
                # 使用检测到的编码
                try:
                    decoded_text = response.content.decode(encoding)
                except UnicodeDecodeError:
                    # 如果解码失败，回退到response.text
                    decoded_text = response.text
            
            if self.debug_mode:
                signal_manager.log_signal.emit(f"使用编码: {encoding}", "main")
            
            # 返回结果
            return {
                'status': status,
                'headers': dict(response.headers),
                'body': decoded_text,
                'time': time_taken,
                'cookies_sent': cookies or {},
                'encoding': encoding
            }
            
        except Exception as e:
            error_msg = f"请求发送失败: {str(e)}"
            signal_manager.log_signal.emit(f"❌ {error_msg}", "main")
            if self.debug_mode:
                signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", "main")
            return {'error': error_msg}

    def display_response(self, result, target="main"):
        """显示响应内容"""
        if 'error' in result:
            signal_manager.log_signal.emit(f"❌ 错误: {result['error']}", target)
            return

        # 显示基本信息
        label = result.get('label', '请求')
        signal_manager.log_signal.emit(f"\n{label} 响应:", target)
        
        # 显示状态码和响应时间
        if 'status' in result and 'time' in result:
            signal_manager.log_signal.emit(f"状态码: {result['status']} ({result['time']})", target)
        
        # 显示请求时间
        if 'request_time' in result:
            signal_manager.log_signal.emit(f"请求时间: {result['request_time']}", target)
            
        # 显示延迟信息（如果有）
        if 'delay' in result and result['delay'] != "无":
            signal_manager.log_signal.emit(f"延迟时间: {result['delay']}", target)
            
        # 显示响应体
        if 'body' in result:
            body = result['body']
            if not body.strip():
                signal_manager.log_signal.emit("(空响应)", target)
            else:
                signal_manager.log_signal.emit("\n响应内容:", target)
                # 尝试解析JSON以便格式化显示
                try:
                    parsed_body = json.loads(body)
                    signal_manager.log_signal.emit(json.dumps(parsed_body, indent=2, ensure_ascii=False), target)
                except:
                    # 如果不是JSON，直接显示
                    signal_manager.log_signal.emit(body, target)
        else:
            signal_manager.log_signal.emit("(无响应内容)", target)
        
        signal_manager.log_signal.emit("", target)  # 添加一个空行作为分隔

    def send_request(self, tab, request_data=None, label=""):
        """发送HTTP请求 - 用于单个请求和后续请求等场景"""
        try:
            target_log = "main" if label in ["请求1", "请求2"] else "followup"
            
            # 获取HTTP请求数据
            if request_data is None:
                # 获取原始HTTP请求
                raw_request = tab.request_input.toPlainText()
                if not raw_request:
                    return {'error': '请求数据包为空'}
                
                # 解析HTTP请求
                parsed = self.parse_http_request(raw_request, force_protocol=None)
            else:
                # 使用传入的请求数据
                parsed = request_data
                
            if 'error' in parsed:
                return parsed
            
            # 获取协议选择
            protocol = None
            if hasattr(tab, 'get_protocol'):
                protocol = tab.get_protocol()
                if self.debug_mode:
                    signal_manager.log_signal.emit(f"使用{protocol.upper()}协议", target_log)
            
            # 如果有强制协议，修改URL
            if protocol:
                url = parsed['url']
                parsed_url = urlparse(url)
                # 替换协议部分
                new_url = f"{protocol}://{parsed_url.netloc}{parsed_url.path}"
                if parsed_url.query:
                    new_url += f"?{parsed_url.query}"
                parsed['url'] = new_url
            
            method = parsed['method']
            url = parsed['url']
            headers = parsed['headers']
            body = parsed['body']

            # 输出请求内容
            if self.debug_mode:
                signal_manager.log_signal.emit("\n" + "="*30 + f" {label} 请求内容 " + "="*30, target_log)
                signal_manager.log_signal.emit(f"请求方法: {method}", target_log)
                signal_manager.log_signal.emit(f"请求URL: {url}", target_log)
                signal_manager.log_signal.emit("\n请求头:", target_log)
                for header_name, header_value in headers.items():
                    signal_manager.log_signal.emit(f"{header_name}: {header_value}", target_log)
                if body:
                    signal_manager.log_signal.emit("\n请求体:", target_log)
                    # 尝试格式化JSON
                    try:
                        json_body = json.loads(body)
                        signal_manager.log_signal.emit(json.dumps(json_body, indent=2, ensure_ascii=False), target_log)
                    except:
                        signal_manager.log_signal.emit(body, target_log)
                signal_manager.log_signal.emit("="*70 + "\n", target_log)
            else:
                # 非调试模式下只显示简要信息
                signal_manager.log_signal.emit(f"\n🚀 {label}: {method} {url}", target_log)
            
            # 记录请求准备时间
            prepare_time = time.strftime("%H:%M:%S", time.localtime())
            prepare_time = prepare_time + ".{:03d}".format(int(time.time() * 1000) % 1000)
            signal_manager.log_signal.emit(f"请求 {label} 准备完成时间: {prepare_time}", target_log)
            
            # 获取延迟时间
            delay = tab.get_delay() if hasattr(tab, 'get_delay') else 0
            if delay > 0:
                signal_manager.log_signal.emit(f"⏱️ {label} 延迟 {delay} 秒...", target_log)
                # 使用同步sleep延迟
                time.sleep(delay)
                now = time.strftime("%H:%M:%S", time.localtime())
                now = now + ".{:03d}".format(int(time.time() * 1000) % 1000)
                signal_manager.log_signal.emit(f"⏱️ {label} 延迟结束，当前时间: {now}", target_log)
            
            # 检查是否包含Cookie
            cookies = {}
            if 'Cookie' in headers:
                cookie_value = headers['Cookie']
                # 解析Cookie
                try:
                    cookie_parts = cookie_value.split(';')
                    for part in cookie_parts:
                        if '=' in part:
                            name, value = part.strip().split('=', 1)
                            cookies[name] = value
                except Exception as e:
                    if self.debug_mode:
                        signal_manager.log_signal.emit(f"Cookie解析错误: {str(e)}", target_log)
                
                # 从headers中移除Cookie，避免重复
                del headers['Cookie']
            
            # 记录请求发送时间
            current_time = time.time()
            request_time = time.strftime("%H:%M:%S", time.localtime(current_time))
            # 添加毫秒
            milliseconds = int((current_time - int(current_time)) * 1000)
            request_time = request_time + ".{:03d}".format(milliseconds)
            
            # 使用requests发送请求
            result = self.send_request_with_requests(method, url, headers, body, cookies)
            
            if 'error' in result:
                signal_manager.log_signal.emit(f"请求错误: {result['error']}", target_log)
                return {'error': result['error'], 'label': label}
            
            signal_manager.log_signal.emit(f"✅ {label} 已收到响应，状态码: {result['status']}", target_log)
            
            # 添加额外信息到结果
            result['label'] = label
            result['delay'] = f"{delay}s" if delay > 0 else "无"
            result['request_time'] = request_time
            
            return result
                    
        except Exception as e:
            signal_manager.log_signal.emit(f"请求错误: {str(e)}", target_log)
            return {'error': str(e), 'label': label}

    # 创建一个线程类用于发送请求
    class RequestThread(threading.Thread):
        def __init__(self, main_window, tab, label):
            super().__init__()
            self.main_window = main_window
            self.tab = tab
            self.label = label
            self.result = None
            
        def run(self):
            """线程执行函数"""
            self.result = self.main_window.send_request(self.tab, label=self.label)

    def on_send_requests(self):
        """按钮点击处理函数"""
        # 防止重复点击，清理之前可能的信号连接
        try:
            signal_manager.result_ready_signal.disconnect(self.process_results)
        except:
            pass  # 如果没有连接，会抛出异常，我们忽略它
            
        # 禁用发送按钮，防止重复点击
        self.send_button.setEnabled(False)
        self.send_button.setText("正在发送请求...")
        
        # 清空响应区域
        self.response_text.clear()
        self.followup_response_text.clear()
        
        # 检查是否启用后续请求
        followup_enabled = self.followup_tab.is_enabled()
        if followup_enabled:
            # 先检查后续请求的设置是否有效
            template = self.followup_tab.get_request_template()
            if not template.strip():
                signal_manager.log_signal.emit("⚠️ 警告：后续请求已启用但请求模板为空", "main")
                self.followup_tab.enable_checkbox.setChecked(False)
                followup_enabled = False
        
        signal_manager.log_signal.emit("🚀 开始并发请求处理...", "main")
        
        # 连接结果处理信号
        signal_manager.result_ready_signal.connect(self.process_results)
        
        # 设置安全超时，确保按钮总是能恢复状态
        QTimer.singleShot(30000, self.check_button_state)
        
        # 创建一个后台线程来处理请求
        thread = threading.Thread(target=self.process_requests_in_thread)
        thread.daemon = True
        thread.start()
    
    def check_button_state(self):
        """检查按钮状态，如果仍然是禁用状态则恢复"""
        if not self.send_button.isEnabled():
            signal_manager.log_signal.emit("⚠️ 请求操作超时，重置按钮状态", "main")
            self.reset_send_button()
    
    def process_requests_in_thread(self):
        """在后台线程中处理请求"""
        try:
            # 创建两个线程，每个线程处理一个请求
            thread1 = self.RequestThread(self, self.tab1, "请求1")
            thread2 = self.RequestThread(self, self.tab2, "请求2")
            
            # 启动线程开始并发请求
            thread1.start()
            thread2.start()
            
            # 等待两个线程完成
            thread1.join()
            thread2.join()
            
            # 收集结果
            results = []
            if thread1.result:
                results.append(thread1.result)
            if thread2.result:
                results.append(thread2.result)
            
            # 使用信号将结果发送到主线程
            signal_manager.result_ready_signal.emit(results)
        except Exception as e:
            print(f"处理请求时出错: {e}")
            # 确保即使出错也恢复按钮状态
            QTimer.singleShot(0, lambda: self.reset_send_button())
    
    def process_results(self, results):
        """处理请求结果并更新UI - 安全地在主线程中调用"""
        try:
            # 断开信号连接，避免内存泄漏
            try:
                signal_manager.result_ready_signal.disconnect(self.process_results)
            except:
                pass  # 忽略已断开的异常
            
            if not results or len(results) == 0:
                signal_manager.log_signal.emit("⚠️ 警告: 未收到任何有效响应", "main")
                self.reset_send_button()
                return
                
            signal_manager.log_signal.emit("✅ 所有请求已完成", "main")
            
            # 显示并发请求结果
            for result in results:
                self.display_response(result, "main")
            
            # 检查是否真的启用了后续请求
            if not self.followup_tab.is_enabled():
                self.reset_send_button()
                return
                
            # 处理后续请求
            self.followup_response_text.append("处理后续请求...\n")
            
            # 再次检查后续请求模板是否为空
            template = self.followup_tab.get_request_template()
            if not template.strip():
                signal_manager.log_signal.emit("❌ 错误: 后续请求模板为空", "followup")
                self.reset_send_button()
                return
            
            # 直接在主线程中处理后续请求准备
            try:
                # 准备后续请求
                followup_request = self.prepare_followup_request(results)
                
                if not followup_request:
                    signal_manager.log_signal.emit("❌ 错误: 无法准备后续请求", "followup")
                    self.reset_send_button()
                    return
                
                if 'error' in followup_request:
                    error_msg = followup_request.get('error', '后续请求准备失败')
                    signal_manager.log_signal.emit(f"❌ 后续请求错误: {error_msg}", "followup")
                    self.reset_send_button()
                    return
                
                # 创建超时定时器 - 使用自定义功能的QTimer
                self.followup_timer = QTimer()
                self.followup_timer.setSingleShot(True)
                self.followup_timer.timeout.connect(self.on_followup_timeout)
                self.followup_timer.start(15000)  # 15秒超时
                
                # 创建一个子线程发送后续请求
                self.start_followup_request(followup_request)
                
            except Exception as e:
                # 捕获后续请求准备中的所有异常
                error_msg = f"后续请求准备异常: {str(e)}"
                signal_manager.log_signal.emit(f"❌ {error_msg}", "followup")
                if self.debug_mode:
                    signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", "followup")
                # 确保出错时也能重置按钮
                self.reset_send_button()
        except Exception as e:
            # 捕获过程中的所有异常
            error_msg = f"结果处理异常: {str(e)}"
            signal_manager.log_signal.emit(f"❌ {error_msg}", "main")
            if self.debug_mode:
                signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", "main")
            # 确保出错时也能重置按钮
            self.reset_send_button()
            
    def start_followup_request(self, followup_request):
        """在子线程中发送后续请求"""
        def send_thread_func():
            try:
                # 发送后续请求
                signal_manager.log_signal.emit("发送后续请求中...", "followup")
                followup_result = self.send_request(self.followup_tab, followup_request, label="后续请求")
                
                # 在主线程中处理结果
                QApplication.instance().postEvent(self, FollowupResultEvent(followup_result))
            except Exception as e:
                # 捕获异常并在主线程中处理
                QApplication.instance().postEvent(self, FollowupErrorEvent(str(e)))
        
        # 启动线程
        thread = threading.Thread(target=send_thread_func)
        thread.daemon = True
        thread.start()
    
    def on_followup_timeout(self):
        """后续请求超时处理函数"""
        signal_manager.log_signal.emit("⚠️ 后续请求处理超时，重置按钮状态", "followup")
        self.reset_send_button()
    
    def event(self, event):
        """重写event处理自定义事件"""
        if isinstance(event, FollowupResultEvent):
            # 取消超时定时器
            if hasattr(self, 'followup_timer') and self.followup_timer is not None:
                self.followup_timer.stop()
                self.followup_timer = None
            
            # 处理后续请求结果    
            self.process_followup_result(event.result)
            return True
        elif isinstance(event, FollowupErrorEvent):
            # 取消超时定时器
            if hasattr(self, 'followup_timer') and self.followup_timer is not None:
                self.followup_timer.stop()
                self.followup_timer = None
                
            # 显示错误信息
            signal_manager.log_signal.emit(f"❌ 后续请求错误: {event.error_message}", "followup")
            # 重置按钮
            self.reset_send_button()
            return True
        
        return super().event(event)
    
    def process_followup_result(self, followup_result):
        """主线程中处理后续请求结果"""
        try:
            if not followup_result:
                signal_manager.log_signal.emit("❌ 错误: 后续请求返回结果为空", "followup")
                self.reset_send_button()
                return
                
            if 'error' in followup_result:
                signal_manager.log_signal.emit(f"❌ 后续请求出错: {followup_result['error']}", "followup")
                self.reset_send_button()
                return
                
            # 获取后续请求的正则表达式
            result_regex = self.followup_tab.get_result_regex()
            
            # 如果设置了结果正则表达式，优先显示匹配结果
            if result_regex and 'body' in followup_result:
                extracted_result = self.extract_with_regex(followup_result['body'], result_regex, "followup")
                if extracted_result:
                    # 显示基本响应信息和匹配结果
                    signal_manager.log_signal.emit("\n后续请求结果:", "followup")
                    signal_manager.log_signal.emit(f"状态码: {followup_result['status']} ({followup_result['time']})", "followup")
                    if 'request_time' in followup_result:
                        signal_manager.log_signal.emit(f"请求时间: {followup_result['request_time']}", "followup")
                    signal_manager.log_signal.emit(f"匹配结果: {extracted_result}\n", "followup")
                else:
                    # 如果没有匹配结果，显示完整响应
                    signal_manager.log_signal.emit("\n正则表达式未匹配到内容，显示完整响应:", "followup")
                    self.display_response(followup_result, "followup")
            else:
                # 如果没有设置正则表达式，显示完整响应
                self.display_response(followup_result, "followup")
                
            signal_manager.log_signal.emit("✅ 后续请求结果处理完成", "followup")
        except Exception as e:
            # 捕获处理过程中的所有异常
            error_msg = f"后续请求结果处理异常: {str(e)}"
            signal_manager.log_signal.emit(f"❌ {error_msg}", "followup")
            if self.debug_mode:
                signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", "followup")
        
        # 最后重置按钮状态
        self.reset_send_button()

    def reset_send_button(self):
        """重置发送按钮状态"""
        try:
            # 确保取消所有可能存在的定时器
            if hasattr(self, 'followup_timer') and self.followup_timer is not None:
                try:
                    self.followup_timer.stop()
                    self.followup_timer = None
                except:
                    pass
            
            # 检查按钮当前状态        
            if not self.send_button.isEnabled():
                self.send_button.setEnabled(True)
                self.send_button.setText("发送并发请求")
                signal_manager.log_signal.emit("✓ 按钮状态已重置，可以发送新请求", "main")
        except Exception as e:
            signal_manager.log_signal.emit(f"❌ 重置按钮状态失败: {str(e)}", "main")

    def extract_with_regex(self, response_text, regex_pattern, target="main"):
        """使用正则表达式从响应中提取数据"""
        try:
            if not regex_pattern:
                return None
                
            # 调试输出，帮助检查正则匹配问题
            if self.debug_mode:
                signal_manager.log_signal.emit(f"正在使用正则表达式: '{regex_pattern}' 查找匹配", target)
                signal_manager.log_signal.emit(f"响应长度: {len(response_text)} 字符", target)
                # 输出响应的前100个字符，帮助调试
                preview = response_text[:min(100, len(response_text))]
                signal_manager.log_signal.emit(f"响应预览: {preview}...", target)
                
                # 检查是否存在转义的引号
                if '\\"' in response_text:
                    signal_manager.log_signal.emit(f"警告: 响应中包含转义的引号 \\\"，可能需要调整正则表达式", target)
            
            # 尝试使用原始的正则表达式
            try:
                # 使用findall查找匹配项
                matches = re.findall(regex_pattern, response_text)
                
                if matches:
                    # 直接返回第一个匹配项
                    return matches[0]
            except Exception as regex_err:
                # 如果原始正则表达式出错，记录错误，但继续尝试其他方法
                if self.debug_mode:
                    signal_manager.log_signal.emit(f"原始正则表达式错误: {str(regex_err)}", target)
            
            # 检查\s是否需要双重转义
            if '\\s' not in regex_pattern and r'\s' in regex_pattern:
                try:
                    # 尝试双重转义
                    fixed_pattern = regex_pattern.replace(r'\s', r'\\s')
                    if self.debug_mode:
                        signal_manager.log_signal.emit(f"尝试修复的正则表达式: {fixed_pattern}", target)
                    matches = re.findall(fixed_pattern, response_text)
                    if matches:
                        return matches[0]
                except Exception as fixed_err:
                    if self.debug_mode:
                        signal_manager.log_signal.emit(f"修复尝试失败: {str(fixed_err)}", target)
            
            # 自动检测并修复其他常见的正则表达式错误
            if '"' in regex_pattern:
                # 检查可能遗漏的转义字符
                common_escapes = ['\\d', '\\w', '\\b', '\\S', '\\s']
                for esc in common_escapes:
                    if esc[1:] in regex_pattern and esc not in regex_pattern:
                        try:
                            fixed_pattern = regex_pattern.replace(esc[1:], esc)
                            if self.debug_mode:
                                signal_manager.log_signal.emit(f"尝试修复转义字符: {fixed_pattern}", target)
                            matches = re.findall(fixed_pattern, response_text)
                            if matches:
                                return matches[0]
                        except Exception:
                            pass
            
            # 提供更详细的匹配失败信息
            if self.debug_mode:
                signal_manager.log_signal.emit(f"正则表达式没有匹配到任何内容", target)
                # 检查是否包含JSON特殊字符，可能需要转义
                if '"' in regex_pattern:
                    signal_manager.log_signal.emit(f"💡 提示: 正则表达式包含引号，请确保JSON中的引号和双引号都已正确处理", target)
                if '\\' not in regex_pattern and ('{' in regex_pattern or '}' in regex_pattern):
                    signal_manager.log_signal.emit(f"💡 提示: 正则表达式包含花括号，可能需要转义: '\\{{' 和 '\\}}'", target)
                if '\\s' not in regex_pattern and r'\s' in regex_pattern:
                    signal_manager.log_signal.emit(f"💡 提示: Python字符串中的\\s应该写成\\\\s才能正确匹配空白字符", target)
                    
            signal_manager.log_signal.emit(f"❌ 正则表达式未匹配到内容", target)
            return None
        except Exception as e:
            signal_manager.log_signal.emit(f"正则表达式提取错误: {str(e)}", target)
            if self.debug_mode:
                signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", target)
            return None

    def prepare_followup_request(self, results):
        """准备后续请求"""
        try:
            if not self.followup_tab.is_enabled():
                return None
                
            # 获取数据源
            source = self.followup_tab.get_source()
            source_idx = 0 if source == "request1" else 1
            
            # 获取响应文本
            if 0 <= source_idx < len(results):
                response_text = results[source_idx].get('body', '')
                signal_manager.log_signal.emit(f"使用 {results[source_idx]['label']} 的响应作为数据源", "followup")
                
                # 调试输出
                if self.debug_mode:
                    preview = response_text[:min(200, len(response_text))]
                    signal_manager.log_signal.emit(f"数据源响应预览: {preview}...", "followup")
            else:
                signal_manager.log_signal.emit(f"⚠️ 警告: 无法找到选择的数据源", "followup")
                return None
            
            # 提取正则表达式结果
            regex = self.followup_tab.get_regex()
            extracted_value = self.extract_with_regex(response_text, regex, "followup") if regex else ""
            
            if not extracted_value and regex:
                signal_manager.log_signal.emit(f"警告: 正则表达式 '{regex}' 未能匹配任何内容", "followup")
                if self.debug_mode:
                    signal_manager.log_signal.emit(f"尝试匹配的原始文本: {response_text[:100]}...", "followup")
            
            # 获取请求模板并替换提取的值
            request_template = self.followup_tab.get_request_template()
            if not request_template.strip():
                signal_manager.log_signal.emit("错误: 后续请求模板为空", "followup")
                return None
                
            if "{{regex_result}}" in request_template:
                if extracted_value:
                    signal_manager.log_signal.emit(f"将提取的值 [{extracted_value}] 替换到请求模板中", "followup")
                    request_template = request_template.replace("{{regex_result}}", extracted_value)
                else:
                    signal_manager.log_signal.emit("⚠️ 警告: 未能提取值但模板中包含{{regex_result}}占位符", "followup")
            
            # 解析请求模板
            return self.parse_http_request(request_template)
        except Exception as e:
            signal_manager.log_signal.emit(f"后续请求准备异常: {str(e)}", "followup")
            if self.debug_mode:
                signal_manager.log_signal.emit(f"错误详情: {traceback.format_exc()}", "followup")
            return {'error': str(e)}

# 自定义事件类型 - 添加在文件顶部import之后
class FollowupResultEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())
    
    def __init__(self, result):
        super().__init__(self.EVENT_TYPE)
        self.result = result

class FollowupErrorEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())
    
    def __init__(self, error_message):
        super().__init__(self.EVENT_TYPE)
        self.error_message = error_message

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    # 设置应用程序样式
    app.setStyle("Fusion")
    
    # 打印版本信息
    signal_manager.log_signal.emit(f"requests版本: {requests.__version__}", "main")
    signal_manager.log_signal.emit(f"Python版本: {sys.version}", "main")
    signal_manager.log_signal.emit("使用requests作为默认HTTP请求库", "main")
    signal_manager.log_signal.emit("使用多线程实现真正的并发请求", "main")
    signal_manager.log_signal.emit("\n---功能说明---", "main")
    signal_manager.log_signal.emit("1. 请求延迟：每个请求可单独设置延时，延时将在发送前等待指定秒数", "main")
    signal_manager.log_signal.emit("2. 延时效果：请求1延时1秒，请求2无延时，则请求2会先发出，请求1晚1秒发出", "main")
    signal_manager.log_signal.emit("3. 响应结果按请求标签分组显示，包含精确的发送时间和状态码", "main")
    signal_manager.log_signal.emit("4. 调试模式可显示更多细节，有助于定位问题", "main")
    signal_manager.log_signal.emit("5. 后续请求可从前两个请求的响应中提取数据并发送新请求", "main")
    signal_manager.log_signal.emit("---使用提示---", "main")
    signal_manager.log_signal.emit("* 如果正则表达式无法匹配，请开启调试模式查看更多信息", "main")
    signal_manager.log_signal.emit("* 设置延时可测试接口竞态条件或保持请求顺序", "main")
    signal_manager.log_signal.emit("* HTTP请求包格式需严格遵循标准格式，头部与正文间用空行分隔\n", "main")
    
    # 运行应用程序
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 