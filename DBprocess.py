import sqlite3
import os
from contextlib import closing

class DBprocess:
    def __init__(self, config_path='config.ini'):
        self.config = self.load_config(config_path)
        self.db_path = self.config.get('DatabaseFilePath', 'data/photodata.db')
        self.ensure_directory_exists(os.path.dirname(self.db_path))
        self.conn = self.create_connection()

    def load_config(self, file_path):
        # 这里可以根据实际情况扩展配置文件的加载逻辑
        config = {
            'DatabaseFilePath': 'data/photodata.db'
        }
        # TODO: 从配置文件加载更多设置
        return config

    def ensure_directory_exists(self, path):
        if not os.path.exists(path):
            os.makedirs(path)

    def create_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            self.create_tables(conn)
            return conn
        except sqlite3.DatabaseError as e:
            print(f"数据库连接失败: {e}")
            return None

    def create_tables(self, conn):
        with closing(conn.cursor()) as cursor:
            # 创建 PhotoInfoTable 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS PhotoInfoTable (
                    PhotoID INTEGER PRIMARY KEY AUTOINCREMENT,
                    FileName TEXT,
                    FileSize INTEGER,
                    FileFormat TEXT,
                    CaptureTime TEXT,
                    IsCaptureTimeAccurate INTEGER,
                    CaptureLocation TEXT,
                    CameraModel TEXT,
                    FilePath TEXT,
                    Thumbnail TEXT,
                    ThumbnailPath TEXT,
                    FileHash TEXT,
                    IsLandscape INTEGER                    
                )
            ''')
            # 创建 Faces 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS Faces (
                    FaceID INTEGER PRIMARY KEY AUTOINCREMENT,
                    FaceHash TEXT,
                    FaceLabel TEXT
                )
            ''')
            # 创建 PhotoFaceLink 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS PhotoFaceLink (
                    PhotoID INTEGER,
                    FaceID INTEGER,
                    FOREIGN KEY (PhotoID) REFERENCES PhotoInfoTable (PhotoID),
                    FOREIGN KEY (FaceID) REFERENCES Faces (FaceID)
                )
            ''')
            # 创建 SWConfig 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS SWConfig (
                    InterfaceColorScheme TEXT,
                    BackgroundImage BLOB,
                    PhotoStoragePath TEXT,
                    DatabaseFilePath TEXT
                )
            ''')
            conn.commit()

    def add_face_info(self, face_hash, face_label):
        query = 'INSERT INTO Faces (FaceHash, FaceLabel) VALUES (?, ?)'
        self.execute_query(query, (face_hash, face_label))
        return self.execute_query('SELECT last_insert_rowid()', fetch_one=True)[0]  # 返回新插入的FaceID

    def execute_query(self, query, params=(), fetch_one=False):
        if self.conn is None:
            print("数据库连接未初始化。")
            return None

        with closing(self.conn.cursor()) as cursor:
            try:
                cursor.execute(query, params)
                self.conn.commit()
                return cursor.fetchone() if fetch_one else cursor.fetchall()
            except sqlite3.DatabaseError as e:
                print(f"执行查询时出错: {query}, 错误: {e}")
                return None

    def get_max_face_id(self):
        query = "SELECT MAX(FaceID) FROM Faces"
        result = self.execute_query(query, fetch_one=True)
        return result[0] if result else None

    def link_face_to_photo(self, photo_id, face_id):
        query = 'INSERT INTO PhotoFaceLink (PhotoID, FaceID) VALUES (?, ?)'
        try:
            self.execute_query(query, (photo_id, face_id))
            print(f"成功关联照片ID {photo_id} 和人脸ID {face_id}")  # 添加调试信息
        except Exception as e:
            print(f"关联照片ID {photo_id} 和人脸ID {face_id} 时出错: {e}")  # 添加错误信息

    def query_photo_info_by_hash(self, file_hash):
        result = self.execute_query('SELECT * FROM PhotoInfoTable WHERE FileHash=?', (file_hash,), True)
        if result:
            print(f"成功查询到照片信息: {result}")  # 添加调试信息
        else:
            print(f"未查询到照片信息，文件哈希: {file_hash}")  # 添加调试信息
        return result

    def query_faces_by_photo(self, photo_id):
        """
        查询与特定照片ID关联的所有人脸信息

        参数:
        photo_id (int): 照片的ID

        返回:
        list: 与此照片关联的所有人脸信息列表，每个元素是一个包含人脸信息的元组
        """
        query = '''
            SELECT F.FaceID, F.FaceHash, F.FaceLabel
            FROM Faces F
            INNER JOIN PhotoFaceLink PFL ON F.FaceID = PFL.FaceID
            WHERE PFL.PhotoID = ?
        '''
        try:  # 添加 try 块，用于捕捉和处理异常
            result = self.execute_query(query, (photo_id,))
            if result is None:  # 添加检查，确保返回结果不是 None
                print(f"没有找到与照片ID {photo_id} 关联的人脸信息")  # 打印调试信息
                return []
            return result
        except Exception as e:  # 捕捉异常
            print(f"查询人脸信息时发生错误: {e}")  # 打印错误信息
            return []

    def add_photo_info(self, photo_info):
        try:
            self.execute_query('''
                        INSERT INTO PhotoInfoTable
                        (FileName, FileSize, FileFormat, CaptureTime, IsCaptureTimeAccurate, CaptureLocation, CameraModel, FilePath, Thumbnail, ThumbnailPath, FileHash, IsLandscape)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', photo_info[:12])
        except Exception as e:
            print(f"添加照片信息失败: {e}")

    def update_photo_info(self, photo_id, new_info):
        self.execute_query('''
                    UPDATE PhotoInfoTable
                    SET FileName=?, FileSize=?, FileFormat=?, CaptureTime=?, IsCaptureTimeAccurate=?, CaptureLocation=?, CameraModel=?, FilePath=?, Thumbnail=?, ThumbnailPath=?, FileHash=?, IsLandscape=?
                    WHERE PhotoID=?
                ''', new_info + (photo_id,))

    # 更新人脸名称的方法
    def update_face_name(self, face_id, new_name):
        try:
            query = "UPDATE Faces SET FaceLabel = ? WHERE FaceID = ?"
            self.execute_query(query, (new_name, face_id))
        except Exception as e:
            print(f"更新人脸名称时出现错误: {e}")

    # 清除所有照片的方法
    def clear_all_photos(self):
        try:
            query = "DELETE FROM Photos"
            self.execute_query(query)
        except Exception as e:
            print(f"清除所有照片时出现错误: {e}")

    def delete_photo_info(self, photo_id):
        try:
            self.execute_query('DELETE FROM PhotoInfoTable WHERE PhotoID=?', (photo_id,))
            self.execute_query('DELETE FROM PhotoFaceLink WHERE PhotoID=?', (photo_id,))  # 同时删除人脸关系表中的信息
        except Exception as e:
            print(f"删除照片信息失败: {e}")

    def query_all_photo_info(self):
        return self.execute_query('SELECT * FROM PhotoInfoTable')
    def query_all_photo_info_face(self):
        return self.execute_query('SELECT * FROM PhotoInfoTable,PhotoFaceLink,Faces where PhotoInfoTable.PhotoID=PhotoFaceLink.PhotoID and PhotoFaceLink.FaceID=Faces.FaceID')

    def query_photo_info(self, photo_id):
        return self.execute_query('SELECT * FROM PhotoInfoTable WHERE PhotoID=?', (photo_id,))

    def update_person_name(self, old_name, new_name):
        self.execute_query('UPDATE Faces SET FaceLabel = ? WHERE FaceLabel = ?', (new_name, old_name))

    def add_sw_config(self, config):
        self.execute_query('INSERT INTO SWConfig VALUES (?, ?, ?, ?)', config)
    
    def query_all_faces(self):
        return self.execute_query('SELECT * FROM Faces')

    def update_sw_config(self, key, new_value):
        self.execute_query(f'UPDATE SWConfig SET {key}=?', (new_value,))

    def get_sw_config(self, key):
        return self.execute_query(f'SELECT {key} FROM SWConfig', fetch_one=True)

    def close(self):
        if self.conn:
            self.conn.close()

# 示例使用
if __name__ == "__main__":
    db = DBprocess()
    # 示例添加照片信息
    db.add_photo_info(('example.jpg', 1024, 'jpg', '2021-01-01', 1, 'New York', 'Canon', '/path/to/photo', '/path/to/thumbnail', 'example_thumb.jpg', 'hash123', 0, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None))
    # 示例查询
    print(db.query_photo_info('example.jpg'))
    # 示例更新配置
    db.add_sw_config(('Light', None, '/path/to/photos', '/path/to/database'))
    # 关闭数据库连接
    db.close()
