import os
import shutil
import hashlib
import time
from PIL import Image, ExifTags, UnidentifiedImageError
from PyQt5.QtCore import QObject, pyqtSignal
from DBprocess import DBprocess  # 确保 DBprocess 模块已按之前建议进行修改
from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
from process_photos import process_photos

class PhotoImporter(QObject):
    request_directory = pyqtSignal()
    import_finished = pyqtSignal(int, int)  # 新信号，参数为导入照片数和生成缩略图数
    import_error = pyqtSignal(str)  # 新增错误处理信号

    def __init__(self, db_processor, photo_storage_path='images', thumbnail_storage_path='thumbnails'):
        super().__init__()
        self.db_processor = db_processor
        self.photo_storage_path = photo_storage_path
        self.thumbnail_storage_path = thumbnail_storage_path
        self.create_directory(self.photo_storage_path)
        self.create_directory(self.thumbnail_storage_path)

    def import_photos(self):
        # 发出信号，请求主线程打开文件夹选择对话框
        self.request_directory.emit()

    def import_from_folder(self, folder_path):
        photo_count = 0
        thumbnail_count = 0
        error_count = 0  # 新增错误计数
        skip_count = 0
        all_file_paths = []
        all_file_hashes = []

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                if file.lower().endswith(('.png', '.jpg', '.jpeg', ".bmp", ".gif", ".tiff", ".webp", ".heic")):
                    try:
                        file_hash = self.calculate_file_hash(file_path)  # 计算文件哈希值
                        if self.db_processor.query_photo_info_by_hash(file_hash):
                            skip_count += 1  # 增加跳过计数
                            print(f"照片 {file_path} 已经存在于数据库中，跳过。")
                            continue

                        if self.process_file(file_path):
                            photo_count += 1
                            thumbnail_count += 1
                            all_file_paths.append(file_path)  # 记录文件路径
                            all_file_hashes.append(self.calculate_file_hash(file_path))  # 记录文件哈希值
                    except Exception as e:
                        error_count += 1
                        self.import_error.emit(f"Error processing file {file_path}: {e}")

        self.import_finished.emit(photo_count, thumbnail_count)  # 发送成功导入的统计信息
        if error_count > 0:
            self.import_error.emit(f"Failed to import {error_count} files.")  # 发送错误统计信息
        if skip_count > 0:
            print(f"Skipped {skip_count} files because they already exist in the database.")  # 输出跳过文件数目
            self.import_error.emit(f"Skipped {skip_count} files due to duplication.")  # 发送跳过文件的统计信息

        # 在所有信息识别和文件存储完成后，调用process_photos进行人脸识别和信息存储
        try:
                # 弹出正在进行人脸识别的信息框
            msgBox = QMessageBox()
            msgBox.setText("正在进行人脸识别，请稍后...")
            msgBox.setStandardButtons(QMessageBox.NoButton)
            msgBox.show()
            QApplication.processEvents()

            # 调用process_photos进行人脸识别和信息存储
            process_photos(list(zip(all_file_paths, all_file_hashes)), self.db_processor)
            #            process_photos(all_file_paths, self.db_processor)

                # 关闭信息框
            msgBox.close()
        except Exception as e:
            print(f"人脸识别或存储操作失败: {e}")
        print(f"成功导入 {photo_count} 张照片。")
        if skip_count > 0:
            self.import_error.emit(f"Skippd to import {skip_count} files due to duplication.")

    def get_decimal_from_dms(self, dms, ref):
        degrees, minutes, seconds = dms
        decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
        if ref in ['S', 'W']:
            decimal = -decimal
        return decimal

    def get_gps_location_from_exif(self, exif_data):
        if 'GPSInfo' not in exif_data:
            return 'Unknown location'

        gps_info = exif_data['GPSInfo']
        gps_latitude = gps_info.get("GPSLatitude")
        gps_latitude_ref = gps_info.get('GPSLatitudeRef')
        gps_longitude = gps_info.get('GPSLongitude')
        gps_longitude_ref = gps_info.get('GPSLongitudeRef')

        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = self.get_decimal_from_dms(gps_latitude, gps_latitude_ref)
            lon = self.get_decimal_from_dms(gps_longitude, gps_longitude_ref)
            return f"{lat}, {lon}"
        return 'Unknown location'

    def extract_capture_info(self, exif_data, file_path):
        if 'DateTimeOriginal' in exif_data:
            capture_date = exif_data['DateTimeOriginal']
            is_capture_time_accurate = 1
        else:
            # 使用文件的创建时间作为备选的拍摄时间
            capture_date = time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(os.path.getctime(file_path)))
            is_capture_time_accurate = 0

        capture_location = self.get_gps_location_from_exif(exif_data)
        return capture_date, capture_location, is_capture_time_accurate

    def process_file(self, file_path):
        file_hash = self.calculate_file_hash(file_path)
        if self.db_processor.query_photo_info_by_hash(file_hash):
            print("File already exists in database")
            return

        try:
            with Image.open(file_path) as image:
                exif_data_raw = image._getexif()  # 获取原始EXIF数据
                if exif_data_raw is not None:  # 检查EXIF数据是否存在
                    exif_data = {ExifTags.TAGS[k]: v for k, v in exif_data_raw.items() if k in ExifTags.TAGS}
                else:
                    exif_data = {}  # 如果没有EXIF数据，使用空字典

                gps_location = self.get_gps_location_from_exif(exif_data)
                capture_date, capture_location, is_capture_time_accurate = self.extract_capture_info(exif_data,
                                                                                                     file_path)
                camera_model = exif_data.get('Make', 'Unknown')

                thumbnail = self.create_thumbnail(image)
                thumbnail_filename = os.path.basename(file_path).replace('.', '_thumb.')
                thumbnail_path = os.path.join(self.thumbnail_storage_path, thumbnail_filename)
                thumbnail.save(thumbnail_path)

                shutil.copy2(file_path, os.path.join(self.photo_storage_path, os.path.basename(file_path)))

                is_capture_time_accurate = 1 if 'DateTimeOriginal' in exif_data else 0
                capture_location = 'Yes' if 'GPSInfo' in exif_data else 'No'  # 简化处理

                photo_info = (
                    os.path.basename(file_path),
                    os.path.getsize(file_path),
                    image.format,
                    capture_date,
                    int(is_capture_time_accurate),
                    gps_location,
                    camera_model,
                    os.path.join(self.photo_storage_path, os.path.basename(file_path)),
                    thumbnail_filename,
                    thumbnail_path,
                    file_hash,
                    0  # IsLandscape
                    )
                self.db_processor.add_photo_info(photo_info)
                return True
        except UnidentifiedImageError:
            print(f"Unidentified image format: {file_path}")
            self.import_error.emit(f"Unidentified image format: {file_path}")
            return False
        except Exception as e:
            print(f"Exception in process_file: {file_path}, Error: {e}")
            self.import_error.emit(f"Exception in process_file: {file_path}, Error: {e}")
            return False

    def calculate_file_hash(self, file_path):
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def create_thumbnail(self, image, size=(128, 128)):
        thumbnail = image.copy()
        thumbnail.thumbnail(size)
        return thumbnail

    def get_exif_data(self, image):
        try:
            return {ExifTags.TAGS[k]: v for k, v in image._getexif().items() if k in ExifTags.TAGS}
        except AttributeError:
            return {}

    def extract_capture_info(self, exif_data, file_path):
        capture_date = exif_data.get('DateTimeOriginal', time.strftime('%Y:%m:%d %H:%M:%S', time.localtime(os.path.getctime(file_path))))
        capture_location = exif_data.get('GPSInfo', 'Unknown location')
        is_capture_time_accurate = 0 if 'DateTimeOriginal' not in exif_data else 1
        return capture_date, capture_location, is_capture_time_accurate

    def create_directory(self, path):
        if not os.path.exists(path):
            os.makedirs(path)
