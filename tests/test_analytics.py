import fakeredis
from sqlalchemy import func, select

from app.analytics import AnalyticsWorker, visitor_key
from app.db import Base, create_db_engine, create_session_factory
from app.models import Click, Link, LinkDailyStat, LinkReferrerDailyStat
from app.timeutils import day_string, utc_now_ts


def test_worker_processes_events(settings) -> None:
    engine = create_db_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        link = Link(code="worker1", long_url="https://example.com/worker")
        session.add(link)
        session.commit()
        link_id = link.id

    redis_client = fakeredis.FakeRedis(decode_responses=True)
    worker = AnalyticsWorker(
        redis_client,
        session_factory,
        stream="events:test",
        group="analytics-test",
        consumer="consumer-test",
    )

    ts = utc_now_ts()
    entries = [
        (
            "1-0",
            {
                "link_id": str(link_id),
                "ts": str(ts),
                "ip_hash": b"visitor-1".hex(),
                "user_agent": "pytest",
                "referrer": "https://news.example.com/article",
            },
        ),
        (
            "2-0",
            {
                "link_id": str(link_id),
                "ts": str(ts),
                "ip_hash": b"visitor-2".hex(),
                "user_agent": "pytest",
                "referrer": "",
            },
        ),
    ]

    assert worker.process_entries(entries) == 2

    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Click)) == 2
        day = day_string(ts)
        daily = session.get(LinkDailyStat, (link_id, day))
        assert daily is not None
        assert daily.clicks == 2
        referrers = {
            row.referrer: row.clicks for row in session.scalars(select(LinkReferrerDailyStat)).all()
        }
        assert referrers == {"news.example.com": 1, "(direct)": 1}

    assert redis_client.pfcount(visitor_key(link_id, day_string(ts))) == 2
    engine.dispose()
