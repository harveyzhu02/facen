import sys
import os
import subprocess
from PyQt5.QtWidgets import QScrollArea, QToolTip, QInputDialog, QScrollBar, QGridLayout, QVBoxLayout, QLabel,  QWidget, QPushButton, QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget, QListWidget, QListWidgetItem, QAction, QToolButton, QMenu, QLabel, QPushButton, QFileDialog, QMessageBox
from PyQt5.QtGui import QIcon, QPixmap, QCursor
from PyQt5.QtCore import QSize, Qt, QTimer, QRunnable, pyqtSlot, pyqtSignal, QObject, QThreadPool
from DBprocess import DBprocess
from photo_importer import PhotoImporter


class ClickableLabel(QLabel):
    def __init__(self, pixmap, file_path, photo_id, parent=None, db_processor = None):
        super().__init__(parent)
        print(f"Creating ClickableLabel for {file_path}")  # 打印信息帮助追踪
        self.setPixmap(pixmap)
        self.file_path = file_path
        self.db_processor = db_processor
        self.parent = parent
        self.photo_id = photo_id

    def mouseDoubleClickEvent(self, event):
        subprocess.Popen([self.file_path], shell=True)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        delete_action = menu.addAction("删除照片")
        action = menu.exec_(event.globalPos())
        if action == delete_action:
            self.delete_photo()

    def delete_photo(self):
        if os.path.exists(self.file_path):
            os.remove(self.file_path)
            self.db_processor.delete_photo_info(self.photo_id)
            self.parent.load_photos()


class CustomFaceLabel(QLabel):
    def __init__(self, text, face_id, parent=None, db_processor = None):
        super().__init__(text, parent)
        self.face_id = face_id
        self.db_processor = db_processor

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        edit_action = menu.addAction("修改姓名")
        action = menu.exec_(event.globalPos())
        if action == edit_action:
            self.edit_name()

    def edit_name(self):
        new_name, ok = QInputDialog.getText(self, '修改姓名', '输入新的姓名:')
        if ok and new_name:
            try:
                self.setText(new_name)
                self.db_processor.update_face_name(self.face_id, new_name)
            except Exception as e:
                QMessageBox.warning(self, "修改错误", f"无法修改姓名: {e}")


class LoadPhotosTask(QRunnable):
    def __init__(self, photo_width_with_padding, photos_per_row):
        super().__init__()
        self.photo_width_with_padding = photo_width_with_padding
        self.photos_per_row = photos_per_row
        self.signals = LoadPhotosTaskSignals()

    @pyqtSlot()
    def run(self):
        try:
            print("子线程：开始加载照片数据")
            # 在子线程中创建新的数据库连接
            db_processor = DBprocess()
            photos = db_processor.query_all_photo_info()
            photo_data = []
            for index, photo in enumerate(photos):
                thumbnail_path = photo[10]
                capture_date = photo[4]  # 假设第 3 个字段是拍摄日期
                if os.path.exists(thumbnail_path):
                    row = index // self.photos_per_row
                    col = index % self.photos_per_row
                    photo_data.append((thumbnail_path, photo[8], row, col, capture_date, photo[0]))
            db_processor.close()  # 确保关闭数据库连接
            self.signals.finished.emit(photo_data)
            print("子线程：照片数据加载完毕，准备发送信号")
        except Exception as e:
            print(f"子线程运行时出现异常：{e}")


class LoadPhotosTaskSignals(QObject):
    finished = pyqtSignal(list)  # 参数为加载完成的照片数据列表


class CustomScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super(CustomScrollArea, self).__init__(parent)
        self.verticalScrollBar().valueChanged.connect(self.showYearMonthTooltip)

        # 用于延迟显示提示的计时器
        self.tooltipTimer = QTimer(self)
        self.tooltipTimer.setSingleShot(True)
        self.tooltipTimer.timeout.connect(self.displayTooltip)

    def showYearMonthTooltip(self):
        # 延迟显示，以避免在快速滚动时频繁更新
        self.tooltipTimer.start(500)

    def displayTooltip(self):
        # 计算并显示年月信息
        if self.parent().showYearMonthInfo:
            year_month = self.calculateYearMonth(self.verticalScrollBar().value())
            if year_month:
                QToolTip.showText(self.mapToGlobal(self.rect().center()), year_month)

    def calculateYearMonth(self, scroll_position):
        # 下面这个逻辑有问题，滚动条的位置年月不应是固定距离，应该是动态计算的。可能需要计算所有照片的数量，计算所有月份数量，对应的长度。
        # 这里需要一些逻辑来根据滚动条的位置确定年月
        # 示例：仅为演示，应根据您的数据结构进行调整
        # 假设每100个滚动单位对应一个月份
        month_index = scroll_position // 100
        year = 2020 + month_index // 12  # 示例年份计算
        month = month_index % 12 + 1      # 示例月份计算
        return f"{year}年{month}月"


class PhotoAlbumApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.threadpool = QThreadPool()
        # 初始化数据库处理和照片导入器
        self.db_processor = DBprocess()
        self.photo_importer = PhotoImporter(self.db_processor)

        # 连接信号和槽
        self.photo_importer.request_directory.connect(self.select_directory)
        self.photo_importer.import_finished.connect(self.on_import_finished)

        # 获取初始化照片数量
        self.initial_photo_count = len(self.db_processor.query_all_photo_info())

        # 设置窗口标题和大小
        self.setWindowTitle("家庭相册智能管理")
        self.setGeometry(100, 100, 800, 600)

        # 创建中央小部件和布局
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # 创建侧边栏和照片区域布局
        left_sidebar_layout = QVBoxLayout()
        photo_area_layout = QVBoxLayout()
        main_layout.addLayout(left_sidebar_layout, 20)
        main_layout.addLayout(photo_area_layout, 80)

        # 创建侧边栏按钮
        self.create_sidebar(left_sidebar_layout)

        # 创建搜索栏和日期按钮
        self.create_search_bar(photo_area_layout)

        # 设置照片区域
        self.setup_photo_area(photo_area_layout)

        # 初始化状态栏
        self.statusBar().showMessage("照片总数: 0 | 已用存储空间: 0MB")

        # 定时清理数据库
#        self.setup_cleanup_timer()

        self.scroll_area = CustomScrollArea() # 使用 CustomScrollArea 鼠标滚动显示日期
        self.showYearMonthInfo = False  # 初始化时不显示年月信息

        self.isDateSortAscending = True  # 初始设置为升序排序

    # 添加一个方法来关闭年月信息的显示
    def disableYearMonthDisplay(self):
        self.showYearMonthInfo = False

    # 在切换到其他状态（如普通视图）时调用这个方法
    def switchToOtherView(self):
        # ...
        self.disableYearMonthDisplay()
        # ...

    def setup_photo_area(self, layout):
        # 创建滚动区域和照片显示区域
        self.scroll_area = QScrollArea()
        self.photo_area = QWidget()
        self.photo_layout = QGridLayout()
        self.photo_layout.setVerticalSpacing(10)
        self.photo_area.setLayout(self.photo_layout)
        self.scroll_area.setWidget(self.photo_area)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)
        self.load_photos()  # 加载并显示照片

    # def setup_cleanup_timer(self):
    #     # 设置定时器以定期清理数据库
    #     self.cleanup_timer = QTimer(self)
    #     self.cleanup_timer.timeout.connect(self.clean_up_database)
    #     self.cleanup_timer.start(600000)  # 每10分钟执行一次

    def create_sidebar(self, layout):
        # 为侧边栏创建按钮
        # icons = ["import", "manage", "edit", "share", "options"]
        # texts = ["导入", "管理", "编辑", "分享", "选项"]
        icons = ["import", "options", "about"]
        texts = ["导入", "选项", "关于"]
        for icon, text in zip(icons, texts):
            button = self.create_tool_button(f"icons/{icon}.svg", text)
            if text == "导入":
                button.clicked.connect(self.import_photos_and_refresh)
            elif text == "选项":
                button.clicked.connect(self.show_options_menu)
            elif text == "关于":
                button.clicked.connect(self.show_about_dialog)  # 连接到显示关于信息的方法
            layout.addWidget(button)

    def create_search_bar(self, layout):
        # 创建搜索栏和日期按钮
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(QLabel("搜索: "))
        date_button = QPushButton("日期")
        date_button.clicked.connect(self.sort_photos_by_date)
        top_bar_layout.addWidget(date_button)
        person_button = QPushButton("人物")
        person_button.clicked.connect(self.sort_photos_by_person)
        top_bar_layout.addWidget(person_button)
        layout.addLayout(top_bar_layout)

    def create_tool_button(self, icon_path, text):
        button_action = QAction(QIcon(icon_path), text, self)
        tool_button = QToolButton()
        tool_button.setDefaultAction(button_action)
        tool_button.setIconSize(QSize(64, 64))  # 图标尺寸增加到原来的2倍
        return tool_button

    def cleanup_resources(self):
        # 关闭数据库连接等资源清理操作
        if self.db_processor:
            self.db_processor.close()

    # def clean_up_database(self):
    #     all_photo_info = self.db_processor.query_all_photo_info()
    #     for photo_info in all_photo_info:
    #         file_path = photo_info[7]
    #         if not os.path.exists(file_path):
    #             self.db_processor.delete_photo_info(photo_info[0])
    #     self.load_photos()

    def closeEvent(self, event):
        # 提示用户关闭信息
        final_photo_count = len(self.db_processor.query_all_photo_info())
        new_photos = final_photo_count - self.initial_photo_count
        reply = QMessageBox.information(self, "关闭提示", f"此次会话新增照片数: {new_photos}",
                                        QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Ok)

        # 根据用户选择处理
        if reply == QMessageBox.Ok:
            self.cleanup_resources()  # 清理资源
            event.accept()  # 接受关闭事件
        else:
            event.ignore()  # 忽略关闭事件

    def load_photos(self):
        try:
            print("主线程：开始清除布局")
            # 清除现有的所有控件
            self.clear_layout(self.photo_layout)
            print("主线程：清除布局完成，开始后台加载任务")
            task = LoadPhotosTask(110, self.calculate_photos_per_row())
            task.signals.finished.connect(self.display_loaded_photos)
            self.threadpool.start(task)
            print("主线程：后台加载任务启动")
            print("照片加载完成")
        except Exception as e:
            QMessageBox.warning(self, "加载照片错误", f"无法加载照片: {e}")
            # # 获取滚动区域的宽度并计算每行图片数
        # scroll_area_width = self.scroll_area.width()
        # photo_width_with_padding = 100 + 10  # 假设每张图片的宽度加上左右边距共100+10
        # photos_per_row = max(1, scroll_area_width // photo_width_with_padding)
        #
        # # 加载并添加图片
        # photos = self.db_processor.query_all_photo_info()
        # for index, photo in enumerate(photos):
        #     thumbnail_path = photo[9]
        #     if os.path.exists(thumbnail_path):
        #         pixmap = QPixmap(thumbnail_path)
        #         if not pixmap.isNull():
        #             photo_label = ClickableLabel(pixmap.scaled(100, 100, Qt.KeepAspectRatio), photo[7], self)
        #             row = index // photos_per_row
        #             col = index % photos_per_row
        #             self.photo_layout.addWidget(photo_label, row, col)
        print("照片加载完成")

    def display_loaded_photos(self, photo_data):
        print("主线程：收到子线程信号，开始更新UI")
        for thumbnail_path, file_path, row, col, capture_date, photo_id in photo_data:
            pixmap = QPixmap(thumbnail_path)
            if not pixmap.isNull():
                photo_widget = QWidget()
                photo_layout = QVBoxLayout(photo_widget)

                photo_label = ClickableLabel(pixmap.scaled(100, 100, Qt.KeepAspectRatio), file_path, photo_id, self, self.db_processor)
                photo_layout.addWidget(photo_label)

                # date_label = QLabel(capture_date)
                # photo_layout.addWidget(date_label)

                self.photo_layout.addWidget(photo_widget, row, col)
            print(f"主线程：正在添加照片 {file_path} 到UI")
        self.update_status_bar()  # 更新状态栏信息
        print("主线程：UI更新完成")

    def calculate_photos_per_row(self):
        scroll_area_width = self.scroll_area.width()
        photo_width_with_padding = 110  # 假设每张图片的宽度加上左右边距共110
        return max(1, scroll_area_width // photo_width_with_padding)

    def resizeEvent(self, event):
        print(f"主线程：检测到窗口大小变化，旧宽度：{self.scroll_area.width()}，新宽度：{event.size().width()}")
        if self.scroll_area.width() != event.size().width():  # 检查宽度是否真的改变
            print("主线程：窗口宽度变化，需要重新加载照片")
            self.load_photos()
        super(PhotoAlbumApp, self).resizeEvent(event)

    def clear_layout(self, layout):
        try:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        except Exception as e:
            QMessageBox.warning(self, "清除布局错误", f"无法清除布局: {e}")

    def clear_data(self):
        reply = QMessageBox.question(self, '确认', '是否删除所有照片数据？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                # 删除 images 目录下的照片
                images_dir = "images"
                if os.path.exists(images_dir):
                    for file in os.listdir(images_dir):
                        file_path = os.path.join(images_dir, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)

                # 删除 thumbnails 目录下的缩略图
                thumbnails_dir = "thumbnails"
                if os.path.exists(thumbnails_dir):
                    for file in os.listdir(thumbnails_dir):
                        file_path = os.path.join(thumbnails_dir, file)
                        if os.path.isfile(file_path):
                            os.remove(file_path)

                # 删除 data 目录下的 photodata.db 文件
                # data_dir = "data"
                # db_file = os.path.join(data_dir, "photodata.db")
                # if os.path.exists(db_file):
                #     os.remove(db_file)

                # 清除数据库中的所有照片信息
                self.db_processor.clear_all_photos()

                QMessageBox.information(self, "数据清除", "照片数据已成功删除。")
                self.load_photos()
                self.update_status_bar()
            except Exception as e:
                QMessageBox.warning(self, "清除数据错误", f"无法清除数据: {e}")

    def calculate_storage_usage(self):
        total_size = sum(os.path.getsize(f[7]) for f in self.db_processor.query_all_photo_info() if os.path.exists(f[7]))
        return total_size // (1024 * 1024)

    def on_import_finished(self, photo_count, thumbnail_count):
        QMessageBox.information(self, "导入完成", f"导入照片数: {photo_count}\n生成缩略图数: {thumbnail_count}")
        self.load_photos()  # 刷新显示区域
        self.update_status_bar()  # 更新状态栏

    def on_import_error(self, error_message):
        QMessageBox.warning(self, "导入错误", error_message)
        self.update_status_bar()  # 即使出错，也更新状态栏

    def open_photo(self, item):
        file_path = item.data(Qt.UserRole)
        if os.path.exists(file_path):
            subprocess.Popen([file_path], shell=True)

    def on_context_menu(self, point):
        item = self.photo_display.itemAt(point)
        if item:
            menu = QMenu()
            delete_action = menu.addAction("删除照片")
            action = menu.exec_(self.photo_display.mapToGlobal(point))
            if action == delete_action:
                self.delete_photo(item)

    def select_directory(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", "")
        if folder:
            self.photo_importer.import_from_folder(folder)

    def sort_photos_by_date(self):

        # 切换排序顺序
        self.isDateSortAscending = not self.isDateSortAscending

        photos = self.db_processor.query_all_photo_info()
        # 根据当前的排序顺序对照片进行排序
        photos.sort(key=lambda x: x[4], reverse=self.isDateSortAscending)

        self.clear_layout(self.photo_layout)

        current_month = None
        row, col = 0, 0
        for index, photo in enumerate(photos):
            thumbnail_path = photo[10]
            capture_date = photo[4]
            photo_month = capture_date[:7]  # 提取年月

            # 将日期格式从 'YYYY-MM' 转换为 'YYYY年MM月'
            formatted_month = f"{photo_month[:4]}年{photo_month[5:7]}月"

            if formatted_month != current_month:
                # 新月份，添加月份标签
                if col != 0:  # 如果当前行不为空，则开始新行
                    row += 1
                    col = 0
                month_label = QLabel(formatted_month)
                self.photo_layout.addWidget(month_label, row, col, 1, self.calculate_photos_per_row())  # 跨越整行
                row += 1  # 移动到下一行
                current_month = formatted_month
                col = 0  # 从新的一行开始

            if os.path.exists(thumbnail_path):
                photo_widget = QWidget()
                photo_layout = QVBoxLayout(photo_widget)

                photo_label = ClickableLabel(QPixmap(thumbnail_path).scaled(100, 100, Qt.KeepAspectRatio), photo[8], photo[0], self, self.db_processor)
                photo_layout.addWidget(photo_label)

                self.photo_layout.addWidget(photo_widget, row, col)
                col += 1
                if col >= self.calculate_photos_per_row():  # 到达每行的图片数量上限
                    row += 1
                    col = 0
        self.showYearMonthInfo = True # 启用显示年月信息

    def show_options_menu(self):
        menu = QMenu(self)
        clear_data_action = menu.addAction("清除数据")
        clear_data_action.triggered.connect(self.clear_data)
        menu.exec_(QCursor.pos())

    def show_about_dialog(self):
        # 创建关于对话框
        about_text = (
            "家庭相册智能管理软件\n\n"
            "版本：0.0.1\n"
            "作者：墨书白\n"
            "指导老师：胡洁婷\n"
            "单位：上海市闵行区七宝第三中学\n\n"
            "本软件用于管理和浏览家庭照片。可以按照照片拍摄日期排序，以及按照人脸分类，能够修改不同人脸对应的名字。\n\n"
            "本软件仍在开发完善中，目前功能比较单一，请大家海涵。\n未来会增加分享、管理功能，改善人脸识别逻辑，采用多线程技术提高处理速度。\n"
            "更多信息，请联系作者 leo_moo@126.com。"
        )
        QMessageBox.information(self, "关于", about_text)

    def sort_photos_by_person(self):

        # 切换排序顺序
        self.isDateSortAscending = not self.isDateSortAscending

        photos = self.db_processor.query_all_photo_info_face()
        photos.sort(key=lambda x: x[14], reverse=self.isDateSortAscending)

        self.clear_layout(self.photo_layout)
           
        row, col = 0, 0
        current_faceid = None
        for index, photo in enumerate(photos):
            thumbnail_path = photo[10]
            capture_faceid = photo[14]

            if capture_faceid != current_faceid:
                current_faceid = capture_faceid
                #
                if col != 0:  # 如果当前行不为空，则开始新行
                    row += 1
                    col = 0
                face_label = CustomFaceLabel(photo[17], capture_faceid, self, self.db_processor)
                self.photo_layout.addWidget(face_label, row, col, 1, self.calculate_photos_per_row())  # 跨越整行
                row += 1  # 移动到下一行
                col = 0  # 从新的一行开始

            if os.path.exists(thumbnail_path):
                photo_widget = QWidget()
                photo_layout = QVBoxLayout(photo_widget)

                photo_label = ClickableLabel(QPixmap(thumbnail_path).scaled(100, 100, Qt.KeepAspectRatio), photo[8], photo[0], self, self.db_processor)
                photo_layout.addWidget(photo_label)

                self.photo_layout.addWidget(photo_widget, row, col)
                col += 1
                if col >= self.calculate_photos_per_row():  # 到达每行的图片数量上限
                    row += 1
                    col = 0

    def update_status_bar(self):
        try:
            # 更新状态栏信息
            total_photos = len(self.db_processor.query_all_photo_info())
            total_size = self.calculate_storage_usage()
            self.statusBar().showMessage(f"照片总数: {total_photos} | 已用存储空间: {total_size}MB")
        except Exception as e:
            QMessageBox.warning(self, "更新状态栏错误", f"无法更新状态栏: {e}")

    def delete_photo(self, item):
        file_path = item.data(Qt.UserRole)
        if os.path.exists(file_path):
            reply = QMessageBox.question(self, '确认', '确定要删除这张照片吗？', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                os.remove(file_path)
                self.db_processor.delete_photo_info(os.path.basename(file_path))
                self.load_photos()
        self.update_status_bar()  # 更新状态栏信息

    def import_photos_and_refresh(self):
        self.photo_importer.import_photos()  # 直接调用 PhotoImporter 的 import_photos 方法

if __name__ == '__main__':
    app = QApplication(sys.argv)
    mainWin = PhotoAlbumApp()
    mainWin.show()
    sys.exit(app.exec_())
