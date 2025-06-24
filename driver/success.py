from .token import set_token
def Success(data):
    if data != None:
        #     print("\n登录结果:")
            print(f"Token: {data['token']}")
            print(f"有效时间: {data['expiry']['expiry_time']} (剩余秒数: {data['expiry']['remaining_seconds']})")
            set_token(data)
    else:
            print("\n登录失败，请检查上述错误信息")