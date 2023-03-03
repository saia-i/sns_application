from flaskr import db, login_manager
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_login import UserMixin, current_user
from sqlalchemy.orm import aliased
from sqlalchemy import and_, or_

from datetime import datetime, timedelta
from uuid import uuid4


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True)
    email = db.Column(db.String(64), unique=True, index=True)
    password = db.Column(db.String(128), default=generate_password_hash("snsflaskapp"))
    picture_path = db.Column(db.Text)
    # 有効か無効かのフラグ(作成時は無効)
    is_active = db.Column(db.Boolean, unique=False, default=False)
    create_at = db.Column(db.DateTime, default=datetime.now)
    update_at = db.Column(db.DateTime, default=datetime.now)

    def __init__(self, username, email):
        self.username = username
        self.email = email

    @classmethod
    def select_user_by_email(cls, email):
        return cls.query.filter_by(email=email).first()

    def validate_password(self, password):
        return check_password_hash(self.password, password)

    def create_new_user(self):
        db.session.add(self)

    @classmethod
    def select_user_by_id(cls, id):
        return cls.query.get(id)

    def save_new_password(self, new_password):
        self.password = generate_password_hash(new_password).decode()
        self.is_active = True

    # UserConnectと紐づける　outer join
    @classmethod
    def search_by_name(cls, username):
        user_connect1 = aliased(
            UserConnect
        )  # from_user_id: 検索相手のID、to_user_id: ログインユーザのIDで紐付ける
        user_connect2 = aliased(
            UserConnect
        )  # to_user_id: 検索相手のID、from_user_id: ログインユーザのIDで紐付ける

        return (
            cls.query.filter(
                cls.username.like(f"%{username}%"),
                cls.id != int(current_user.get_id()),  # 検索しているユーザは取得しない
                cls.is_active == True,
            )
            .outerjoin( 
                user_connect1,  # テーブル名
                and_(  # ON user_connect1.from_user_id == users.id AND user_connect1.to_user_id == ?
                    user_connect1.from_user_id == cls.id,
                    user_connect1.to_user_id == current_user.get_id(),
                ),
            )
            .outerjoin(
                user_connect2,
                and_(
                    user_connect2.from_user_id == current_user.get_id(),
                    user_connect2.to_user_id == cls.id,
                ),
            )
            .with_entities(
                cls.id,
                cls.username,
                cls.picture_path,
                user_connect1.status.label("joined_status_to_from"),
                user_connect2.status.label("joined_status_from_to"),
            )  # 必要なカラムだけ取り出す
            .all()
        )
        
    @classmethod
    def select_friends(cls):
        return (
            cls.query.join(
                UserConnect,
                or_(
                    and_(
                        UserConnect.to_user_id == cls.id,
                        UserConnect.from_user_id == current_user.get_id(),
                        UserConnect.status == 2
                    ),
                    and_(
                        UserConnect.from_user_id == cls.id,
                        UserConnect.to_user_id == current_user.get_id(),
                        UserConnect.status == 2
                    )
                )
            ).with_entities(
                cls.id,cls.username,cls.picture_path
            ).all()
        )
    @classmethod
    def select_requested_friends(cls):
        return (
            cls.query.join(
                UserConnect,
                and_(
                    UserConnect.from_user_id == cls.id,
                     UserConnect.to_user_id == current_user.get_id(),
                    UserConnect.status == 1
                )
            ).with_entities(
                cls.id,cls.username,cls.picture_path
            ).all()
        )
        
    @classmethod
    def select_requesting_friends(cls):
        return (
            cls.query.join(
                UserConnect,
                and_(
                    UserConnect.from_user_id == current_user.get_id(),
                     UserConnect.to_user_id == cls.id,
                    UserConnect.status == 1
                )
            ).with_entities(
                cls.id,cls.username,cls.picture_path
            ).all()
        )

# パスワードリセット時に利用する
class PasswordResetToken(db.Model):
    __tablename__ = "password_reset_tokens"
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(64), unique=True, index=True, server_default=str(uuid4))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expire_at = db.Column(db.DateTime, default=datetime.now)
    create_at = db.Column(db.DateTime, default=datetime.now)
    update_at = db.Column(db.DateTime, default=datetime.now)

    def __init__(self, token, user_id, expire_at):
        self.token = token
        self.user_id = user_id
        self.expire_at = expire_at

    @classmethod
    def publish_token(cls, user):
        # パスワード設定用のURLを生成
        token = str(uuid4())
        new_token = cls(token, user.id, datetime.now() + timedelta(days=1))
        db.session.add(new_token)
        return token

    @classmethod
    def get_user_id_by_token(cls, token):
        now = datetime.now()
        recode = (
            cls.query.filter_by(token=str(token)).filter(cls.expire_at > now).first()
        )
        if recode:
            return recode.user_id
        else:
            return None

    @classmethod
    def delete_token(cls, token):
        cls.query.filter_by(token=str(token)).delete()


class UserConnect(db.Model):
    __tablename__ = "user_connects"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True)
    status = db.Column(db.Integer, unique=False, default=1)  # 1：申請中、2：承認済み
    create_at = db.Column(db.DateTime, default=datetime.now)
    update_at = db.Column(db.DateTime, default=datetime.now)

    def __init__(self, from_user_id, to_user_id):
        self.from_user_id = from_user_id
        self.to_user_id = to_user_id

    def create_new_connect(self):
        db.session.add(self)

    @classmethod
    def select_by_from_user_id(cls, from_user_id):
        return cls.query.filter_by(
            from_user_id=from_user_id, to_user_id=current_user.get_id()
        ).first()

    def update_status(self):
        self.status = 2
        self.update_at = datetime.now()
        
    @classmethod
    def is_friend(cls,to_user_id):
        user=cls.query.filter(
            or_(
                and_(
                    UserConnect.from_user_id==current_user.get_id(),
                    UserConnect.to_user_id==to_user_id,
                    UserConnect.status==2
                ),
                and_(
                    UserConnect.from_user_id==to_user_id,
                    UserConnect.to_user_id==current_user.get_id(),
                    UserConnect.status==2
                )
            )
        ).first()
        return True if user else False


class Message(db.Model):
    
    __tablename__="messages"
    
    id=db.Column(db.Integer,primary_key=True)
    from_user_id=db.Column(db.Integer,db.ForeignKey("users.id"),index=True)
    to_user_id=db.Column(db.Integer,db.ForeignKey("users.id"),index=True)
    is_read=db.Column(db.Boolean,default=False)
    message=db.Column(db.Text)
    create_at = db.Column(db.DateTime, default=datetime.now)
    update_at = db.Column(db.DateTime, default=datetime.now)
    
    def __init__(self,from_user_id,to_user_id,message):
        self.from_user_id=from_user_id
        self.to_user_id=to_user_id
        self.message=message
        
    def create_message(self):
        db.session.add(self)
        
    @classmethod
    def get_friend_messages(cls,id1,id2):
        return cls.query.filter(
            or_(
                and_(
                    cls.from_user_id==id1,
                    cls.to_user_id==id2
                ),
                and_(
                    cls.from_user_id==id2,
                    cls.to_user_id==id1
                )
            )
        ).order_by(cls.id).all()
        
    @classmethod
    def update_is_read_by_ids(cls,ids):
        cls.query.filter(cls.id.in_(ids)).update(
            {'is_read':1},
            # fetchを指定することでレコードを更新する前に、SELECTを実行して更新対象のレコードを取得する
            synchronize_session="fetch"
        )
        
    @classmethod
    def select_not_read_messages(cls,from_user_id,to_user_id):
        return cls.query.filter(
            and_(
                cls.from_user_id==from_user_id,
                cls.to_user_id==to_user_id,
                cls.is_read==False
            )
        ).order_by(cls.id).all()
        
    