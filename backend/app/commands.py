"""Flask CLI commands: flask init-db / seed / reset-db."""
import click

from .extensions import db
from .models import Exceedance, Measurement, Position, Station, User


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create database tables."""
        db.create_all()
        click.echo("数据库表已创建")

    @app.cli.command("ensure-admin")
    @click.option("--username", default="admin", show_default=True)
    @click.option("--password", default="air123456", show_default=True)
    @click.option("--name", default="系统管理员", show_default=True)
    def ensure_admin(username, password, name):
        """Create the administrator account (and its position) when absent."""
        position = Position.query.filter_by(code="admin").first()
        if position is None:
            position = Position(code="admin", name="系统管理员", is_admin=True, can_proxy=True)
            db.session.add(position)
            db.session.flush()
        user = User.query.filter_by(username=username).first()
        if user is None:
            user = User(username=username, display_name=name, position=position, active=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            click.echo("管理员已创建: %s / %s" % (username, password))
        else:
            click.echo("管理员账号已存在: %s(如需改密请用 set-password)" % username)

    @app.cli.command("set-password")
    @click.argument("username")
    @click.argument("password")
    def set_password(username, password):
        """Reset a user's login password."""
        user = User.query.filter_by(username=username).first()
        if user is None:
            click.echo("用户不存在: %s" % username)
            raise SystemExit(1)
        user.set_password(password)
        db.session.commit()
        click.echo("已重置 %s 的登录密码" % username)

    @app.cli.command("seed")
    @click.option("--days", default=5, show_default=True, help="生成最近多少天的数据")
    @click.option("--force", is_flag=True, help="已有数据时仍然追加写入")
    def seed(days, force):
        """Load demo stations and monitoring records."""
        from .seed import seed_demo_data

        if Station.query.count() and not force:
            click.echo("已存在监测点数据, 如确需追加请使用 --force")
            return
        db.create_all()
        totals = seed_demo_data(days=days)
        click.echo(
            "演示数据写入完成: 监测点 %(stations)s 个, 监测数据 %(measurements)s 条, "
            "超标记录 %(exceedances)s 条" % totals
        )

    @app.cli.command("reset-db")
    @click.option("--with-demo/--empty", default=True, help="是否写入演示数据")
    def reset_db(with_demo):
        """Drop all tables, recreate them and optionally load demo data."""
        from .seed import reset_database, seed_demo_data

        reset_database()
        click.echo("数据库已重置")
        if with_demo:
            totals = seed_demo_data()
            click.echo("演示数据写入完成: %s" % totals)

    @app.cli.command("stats")
    def stats():
        """Print a short record summary."""
        click.echo(
            "监测点 %d 个 / 监测数据 %d 条 / 超标记录 %d 条 / 账号 %d 个 / 岗位 %d 个"
            % (
                Station.query.count(),
                Measurement.query.count(),
                Exceedance.query.count(),
                User.query.count(),
                Position.query.count(),
            )
        )
