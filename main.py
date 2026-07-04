import os
import time
import json
from get_token import get_access_token
from concurrent.futures import ThreadPoolExecutor
from utils import random_email, generate_strong_password
from controllers.patchright_controller import PatchrightController
from controllers.playwright_controller import PlaywrightController
from controllers.geekez_controller import GeekEzController



# --- 不确定有无帮助 ---
# 0. 视窗大小
# 1. CDP 检测：wait_for_timeout --> time.sleep()
# 2. 使用 launch_persistent_context 
# 3. 避免短时间访问
# 4. 模拟真人轨迹

def process_single_flow(controller):
    page = None

    try:
        page = controller.get_thread_page()

        email = random_email()
        password = generate_strong_password()

        # 调用 controller 特定的注册方法
        result = controller.outlook_register(page, email, password)

        if result and not controller.enable_oauth2:
            controller.clean_up(page, "done_browser")
            return True
        elif not result:
            return False

        token_result = get_access_token(page, email)
        if token_result[0]:
            refresh_token, access_token, expire_at =  token_result
            with open(os.path.join(os.path.dirname(__file__), 'Results', 'outlook_token.txt'), 'a', encoding='utf-8') as f2:
                f2.write(f"{email}{controller.email_suffix}---{password}---{refresh_token}---{access_token}---{expire_at}\n") 
            print(f'[Success: TokenAuth] - {email}{controller.email_suffix}')
            controller.clean_up(page, "done_browser")
            return True
        else:
            return False

    except Exception as e:
        print(e)
        return False

def run_concurrent_flows(controller, concurrent_flows=10, max_tasks=100):
    task_counter = 0
    succeeded_tasks = 0
    failed_tasks = 0

    with ThreadPoolExecutor(max_workers=concurrent_flows) as executor:
        running_futures = set()

        while task_counter < max_tasks or len(running_futures) > 0:
            done_futures = {f for f in running_futures if f.done()}
            for future in done_futures:
                try:
                    if future.result():
                        succeeded_tasks += 1
                    else:
                        failed_tasks += 1
                except Exception as e:
                    failed_tasks += 1
                    print(e)
                running_futures.remove(future)

            while len(running_futures) < concurrent_flows and task_counter < max_tasks:
                new_future = executor.submit(process_single_flow, controller)
                running_futures.add(new_future)
                task_counter += 1
                if max_tasks > 1 and task_counter % (max_tasks // 2) == 0:
                    print(f"已提交 {task_counter}/{max_tasks} 任务.")
                elif max_tasks == 1:
                    print(f"已提交 {task_counter}/{max_tasks} 任务.")

            time.sleep(0.5)

    print(f"\n[Result] - 共: {max_tasks}, 成功 {succeeded_tasks}, 失败 {failed_tasks}")
    return succeeded_tasks, failed_tasks


if __name__ == "__main__":

    with open('config.json', 'r', encoding='utf-8') as f:
        data = json.load(f) 
    os.makedirs("Results", exist_ok=True)

    max_tasks = data["max_tasks"]
    concurrent_flows = data["concurrent_flows"]

    if data["choose_browser"] == "patchright":
        selected_controller = PatchrightController()
    elif data["choose_browser"] == "playwright":
        selected_controller = PlaywrightController()
    elif data["choose_browser"] == "geekez":
        # 连接到 GeekEZ Browser
        geekez_port = data.get("geekez_debug_port", 9222)
        selected_controller = GeekEzController(debug_port=geekez_port)
    else:
        print("不支持的浏览器类型，填写 patchright、playwright 或 geekez")
        exit(1)
  

    try:
        succeeded, failed = run_concurrent_flows(selected_controller, concurrent_flows, max_tasks)
    except:
        succeeded, failed = 0, max_tasks
    finally:
        if failed > 0 and succeeded < max_tasks:
            input("\n有任务失败，浏览器已保持打开。检查完毕后按 Enter 键关闭所有浏览器并退出...")
        selected_controller.clean_up(type="all_browser")