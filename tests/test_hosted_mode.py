from app import create_app


def test_hosted_mode_blocks_demo_even_under_test_and_sets_secure_cookie():
    app=create_app({'TESTING':True,'HOSTED_MODE':True,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    client=app.test_client()
    assert client.get('/demo/request').status_code==404
    assert client.get('/api/requests/1').status_code==401
    assert client.post('/api/requests',json={}).status_code==401
    response=client.get('/login',headers={'X-Forwarded-Proto':'https'})
    assert response.status_code==200
    cookie=response.headers['Set-Cookie']
    assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=Lax' in cookie
    assert app.debug is False


def test_local_demo_route_preserved():
    app=create_app({'TESTING':True,'HOSTED_MODE':False,'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:'})
    assert app.test_client().get('/demo/request').status_code==200
