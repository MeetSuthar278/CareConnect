"""Read-only coordinator totals from saved workflow and Yes/No feedback data."""
from sqlalchemy import text
from app.services.guest_requests import DISPLAY_STATUS


def report_data(database):
    counts=database.execute(text('SELECT status,COUNT(*) AS count FROM service_requests GROUP BY status ORDER BY status')).mappings().all()
    feedback=database.execute(text('''SELECT COUNT(*) AS count,
        COALESCE(SUM(CASE WHEN is_helpful=TRUE THEN 1 ELSE 0 END),0) AS helpful
        FROM feedback WHERE is_helpful IS NOT NULL''')).mappings().one()
    total=sum(row['count'] for row in counts)
    completed=next((row['count'] for row in counts if row['status']=='completed'),0)
    orgs=database.execute(text("SELECT COUNT(*) FROM organizations WHERE status='approved'")).scalar_one()
    categories=database.execute(text('''SELECT COALESCE(c.name,'Uncategorized') AS name,COUNT(*) AS count,
        SUM(CASE WHEN sr.status='completed' THEN 1 ELSE 0 END) AS completed
        FROM service_requests sr JOIN services s ON s.service_id=sr.service_id
        LEFT JOIN service_categories c ON c.category_id=s.category_id
        GROUP BY c.category_id,c.name ORDER BY name''')).mappings().all()
    totals=dict(requests=total,completed=completed,organizations=orgs,feedback_count=feedback['count'],
                helpful_percentage=round(100*feedback['helpful']/feedback['count'],1) if feedback['count'] else None)
    return dict(totals=totals,by_status=[dict(name=DISPLAY_STATUS.get(row['status'],row['status']),count=row['count']) for row in counts],by_category=categories)
