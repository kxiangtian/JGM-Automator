from target import TargetType
from building import BuildingType
from multiprocessing import Queue
from config import Reader
from cv import UIMatcher
from random import choice
from datetime import datetime
import uiautomator2 as u2
import logging
import time
import prop

BASIC_FORMAT = "[%(asctime)s] %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(BASIC_FORMAT, DATE_FORMAT)

chlr = logging.StreamHandler()  # 输出到控制台的handler
chlr.setFormatter(formatter)

fhlr = logging.FileHandler("logging.log")  # 输出到文件的handler
fhlr.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel('INFO')
logger.addHandler(chlr)
logger.addHandler(fhlr)


def elect(order_list_len, iter_round):
    res = []
    for i in range(1, order_list_len + 1):
        if iter_round % i == 0:
            res.append(i - 1)
    return res


class Automator:
    def __init__(self, device: str, keyboard: Queue):
        """
        device: 如果是 USB 连接，则为 adb devices 的返回结果；如果是模拟器，则为模拟器的控制 URL 。
        """
        self.d = u2.connect(device)
        self.config = Reader()
        self.upgrade_iter_round = 0
        self.keyboard = keyboard
        self.command_mode = False
        self._check_uiautomator()
        self.time_start_working = time.time()
        self.refresh_times = 0
        self.delivered_times = 0

    def _need_continue(self):
        if not self.keyboard.empty():
            # 不在命令模式下时才接受回车暂停
            if not self.command_mode:
                txt = self.keyboard.get()
                # logger.info('txt1:' + txt)
                if txt == prop.END:
                    logger.info('End')
                    return False
                logger.info('Pause')
            txt = self.keyboard.get()
            # logger.info('txt2:' + txt)
            if txt == prop.END:
                logger.info('End')
                return False
            # 判断是否输入命令
            elif txt.split(' ')[0] == prop.RUN:
                # logger.info(txt.split(' ')[1:])
                cmd = txt.split(' ')[1]
                # 命令 - 升至 x 级
                if cmd == prop.UPGRADE_TO:
                    try:
                        target_level = int(txt.split(' ')[2])
                    except Exception:
                        logger.warn("Invalid number. Ignored.")
                    else:
                        self._upgrade_to(target_level)
                    # logger.info('target_level: ' + str(target_level))
                # 命令 - 升级 x 次
                elif cmd == prop.UPGRADE_TIMES:
                    try:
                        input_num = int(txt.split(' ')[2])
                    except Exception:
                        logger.warn("Invalid number. Ignored.")
                    else:
                        self._upgrade_times(input_num)
                # 命令 - 命令模式
                elif cmd == prop.COMMAND_MODE:
                    if txt.split(' ')[2] == 'on':
                        self.command_mode = True
                        logger.info('Enter command mode.')
                    elif txt.split(' ')[2] == 'off':
                        self.command_mode = False
                        logger.info('Exit command mode.')
                        self._return_main_area()
                    else:
                        logger.warn("Unknown parameter. Ignored.")
                # 命令 - 拆红包
                elif cmd == prop.UNPACK:
                    pack_type = txt.split(' ')[2]
                    if pack_type in ['s', 'm', 'l']:
                        try:
                            input_num = int(txt.split(' ')[3])
                        except Exception:
                            logger.warn("Invalid number. Ignored.")
                        else:
                            self._unpack_times(pack_type, input_num)
                            logger.info('Unpack complete.')
                    else:
                        logger.warn("Unknown parameter. Ignored.")
                elif cmd == prop.OPEN_ALBUM:
                    try:
                        input_num = int(txt.split(' ')[2])
                    except Exception:
                        logger.warn("Invalid number. Ignored.")
                    else:
                        self._open_albums(input_num)
                        logger.info('Open complete.')
                # 无法识别命令
                else:
                    logger.warn("Unknown command. Ignored.")
                if not self.command_mode:
                    logger.info('Restart')
                return True
            else:
                logger.info('Restart')
                return True
        else:
            return True

    def start(self):
        """
        启动脚本，请确保已进入游戏页面。
        """
        tmp_upgrade_last_time = time.time()
        logger.info("Start Working")
        while True:
            # 检查是否有键盘事件
            if not self._need_continue():
                logger.info('-' * 30)
                pass_time = time.time() - self.time_start_working
                logger.info(f"本次启动运行了 {int(pass_time // 3600)} 小时 {int(pass_time % 3600 // 60)} 分钟 {round(pass_time % 60, 2)} 秒")
                logger.info(f"重启了 {self.refresh_times} 次， 检测到 {self.delivered_times} 次货物（非总送货次数）")
                break
            
            # 进入命令模式后不继续执行常规操作
            if self.command_mode:
                continue

            # 更新配置文件
            self.config.refresh()

            if self.config.debug_mode:
                None
                # 重启游戏法
                # self._refresh_train_by_restart()
                
                # 重连 wifi 法
                # self._refresh_train_by_reconnect()
            
            # 是否检测货物
            if self.config.detect_goods:
                logger.info('-' * 30)
                logger.info("Start matching goods")
                # 获取当前屏幕快照
                screen = self._safe_screenshot()
                # 判断是否出现货物。
                has_goods = False
                refresh_flag = False
                for target in self.config.goods_2_building_seq.keys():
                    has_goods |= self._match_target(screen, target)
                # 如果需要刷新火车并且已送过目标货物
                if has_goods and self.config.refresh_train:
                    refresh_flag = True
                    logger.info("All target goods delivered.")
                # 如果需要刷新火车并且未送过目标货物
                elif self.config.refresh_train:
                    for target in self.config.goods_2_building_seq_excpet_target.keys():
                        if UIMatcher.match(screen, target) is not None:
                            has_goods = True
                            break
                    if has_goods:
                        refresh_flag = True
                        logger.info("Train detected with no target goods.")
                    else:
                        logger.info("Train not detected.")
                if refresh_flag:
                    # 刷新火车
                    logger.info("Refresh train.")
                    logger.info("-" * 30)
                    self.refresh_times += 1
                    self._refresh_train_by_restart()                    
                else:
                    logger.info("End matching")

            # 简单粗暴的方式，处理 “XX之光” 的荣誉显示。
            # 当然，也可以使用图像探测的模式。
            self.d.click(550, 1650)

            # 滑动屏幕，收割金币。
            # logger.info("swipe")
            self._swipe()

            # 升级建筑
            tmp_upgrade_interval = time.time() - tmp_upgrade_last_time
            if tmp_upgrade_interval >= self.config.upgrade_interval_sec:
                if self.config.upgrade_type_is_assign is True:
                    self._assigned_uprade()
                tmp_upgrade_last_time = time.time()
            else:
                logger.info(f"Left {round(self.config.upgrade_interval_sec - tmp_upgrade_interval, 2)}s to upgrade")

            time.sleep(self.config.swipe_interval_sec)
        logger.info('Sub process end')

    def _swipe(self):
        """
        滑动屏幕，收割金币。
        """
        for i in range(3):
            # 横向滑动，共 3 次。
            sx, sy = self._get_position(i * 3 + 1)
            ex, ey = self._get_position(i * 3 + 3)
            self.d.swipe(sx, sy, ex, ey)

    @staticmethod
    def _get_position(key):
        """
        获取指定建筑的屏幕位置。

        ###7#8#9#
        ##4#5#6##
        #1#2#3###
        """
        return prop.BUILDING_POS.get(key)

    def _get_target_position(self, target: TargetType):
        """
        获取货物要移动到的屏幕位置。
        """
        return self._get_position(self.config.goods_2_building_seq.get(target))

    def _match_target(self, screen, target: TargetType):
        """
        探测货物，并搬运货物。
        """
        # 由于 OpenCV 的模板匹配有时会智障，故我们探测次数实现冗余。
        counter = 6
        logged = False
        while counter != 0:
            counter = counter - 1

            # 使用 OpenCV 探测货物。
            result = UIMatcher.match(screen, target)

            # 若无探测到，终止对该货物的探测。
            # 实现冗余的原因：返回的货物屏幕位置与实际位置存在偏差，导致移动失效
            if result is None:
                break

            rank = result[-1]
            result = result[:2]
            sx, sy = result
            # 获取货物目的地的屏幕位置。
            ex, ey = self._get_target_position(target)

            if not logged:
                self.delivered_times += 1
                logger.info(f"Detect {target} at ({sx},{sy}), rank: {rank}")
                logged = True

            # 搬运货物。
            self.d.swipe(sx, sy, ex, ey)
        # 侧面反映检测出货物
        return logged
    
    def _assigned_uprade(self):
        logger.info("Start assigned upgrading")
        self.d.click(*prop.BUILDING_DETAIL_BTN)
        time.sleep(0.5)
        self.d.click(*self._get_position(self.config.assigned_building_pos))
        time.sleep(0.5)
        self.d.long_click(prop.BUILDING_UPGRADE_BTN[0], prop.BUILDING_UPGRADE_BTN[1],
                          self.config.upgrade_press_time_sec)
        time.sleep(0.5)
        self.d.click(*prop.BUILDING_DETAIL_BTN)
        logger.info("Upgrade complete")

    def _upgrade_to(self, target_level):
        """
        target_level: 目标等级
        升至 target_level 级
        利用 Tesseract 识别当前等级后点击升级按钮 target_level - 当前等级次
        """
        screen = self._safe_screenshot()
        screen = UIMatcher.pre_building_panel(screen)
        tmp = UIMatcher.cut(screen, prop.BUILDING_INFO_PANEL_LEVEL_POS, (120, 50))
        # import cv2
        # cv2.imwrite("./tmp/screen.jpg", screen)
        tmp = UIMatcher.plain(tmp)
        tmp = UIMatcher.fill_color(tmp)
        tmp = UIMatcher.plain(tmp)
        txt = UIMatcher.image_to_txt(tmp, plus='-l chi_sim --psm 7')
        txt = UIMatcher.normalize_txt(txt)
        try:
            cur_level = int(txt)
            logger.info(f'Current level -> {cur_level}')
        except Exception:
            logger.warning(f'Current level -> {txt}')
            return
        click_times = target_level - cur_level
        self._upgrade_times(click_times)

    def _upgrade_times(self, click_times: int):
        """
        click_times: 点击/升级次数
        执行点击升级按钮的操作 click_times 次
        """
        # assert(times >= 0)
        while click_times > 0:
            click_times -= 1
            bx, by = prop.BUILDING_INFO_PANEL_UPGRADE_BTN
            self.d.click(bx, by)
            time.sleep(0.015)
        logger.info("Upgrade complete")
        # 非命令模式下完成操作后返回主界面以继续常规流程
        if not self.command_mode:
            self._return_main_area()

    def _return_main_area(self):
        """
        通过点击两次导航栏内建设按钮来回到主界面
        """
        time.sleep(0.5)
        tx, ty = prop.CONSTRUCT_BTN
        self.d.click(tx, ty)
        time.sleep(0.1)
        self.d.click(tx, ty)
        time.sleep(0.5)

    def _unpack_times(self, pack_type, sum: int):
        # 红包标题栏坐标 开红包后点这里直到开完这个红包
        tx, ty = prop.REDPACKET_TITLE_POS
        if pack_type == 'm':
            bx, by = prop.REDPACKET_BTN_M
            t = 6
        elif pack_type == 'l':
            bx, by = prop.REDPACKET_BTN_L
            t = 12
        else:
            # logger.inf("暂不支持开小红包")
            bx, by = prop.REDPACKET_BTN_S
            t = 3
        while sum > 0:
            sum -= 1
            self.d.click(bx, by)
            time.sleep(0.5)
            self.d.click(tx, ty)
            time.sleep(0.5)
            # 防止意外多点几下 例如升星或开出史诗
            for i in range(t):
                # logger.info(f"第{i}次点击")
                self.d.click(tx, ty)
                time.sleep(0.5)
    
    def _open_albums(self, sum: int):
        tx, ty = prop.ALBUM_BTN
        bx, by = prop.REDPACKET_TITLE_POS
        while sum > 0:
            sum -= 1
            self.d.click(tx, ty)
            time.sleep(1)
            for i in range(5):
                # logger.info(f"第{i}次点击")
                self.d.click(bx, by)
                time.sleep(0.5)

    def _is_good_to_go(self):
        screen = self._safe_screenshot()
        return UIMatcher.match(screen, TargetType.Rank_btn) is not None

    def _refresh_train_by_restart(self):
        """
        通过重启游戏的方法来刷新火车
        全程用时大约在 20s 左右
        qq 账号测试不用授权 20s 左右
        """
        time_before_restart = time.time()
        self.d.app_stop("com.tencent.jgm")
        self.d.app_start("com.tencent.jgm", activity=".MainActivity")
        time.sleep(5)
        good_to_go = False
        while not good_to_go:
            if self._is_good_to_go():
                good_to_go = True
                logger.info(f"Refresh train costs {round(time.time() - time_before_restart, 2)}s.")
            else:
                time.sleep(1)

    def _refresh_train_by_reconnect(self):
        """
        通过关闭开启 wifi 的方法刷新火车
        要重新登陆+授权 暂时弃用
        """
        self.d.press("home")
        time.sleep(0.5)
        logger.info("Wifi disable.")
        logger.info(self.d.adb_shell("svc wifi disable"))
        time.sleep(0.5)
        logger.info("Wifi enable.")
        logger.info(self.d.adb_shell("svc wifi enable"))
        time.sleep(5)
        self.d.app_start("com.tencent.jgm", activity=".MainActivity")

    def _check_uiautomator(self):
        """
        检查 uiautomator 运行状态
        """
        if not self.d.uiautomator.running():
            self.d.reset_uiautomator()

    def _safe_screenshot(self):
        self._check_uiautomator()
        return self.d.screenshot(format="opencv")
