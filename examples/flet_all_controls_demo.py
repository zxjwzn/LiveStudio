from __future__ import annotations

import flet as ft

ControlList = list[ft.Control]


def main(page: ft.Page) -> None:
    page.title = "Flet 0.28.3 全组件示例"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 0
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 1200
    page.window.height = 860

    output = ft.Text("事件输出：等待操作", selectable=True)
    drag_target_text = ft.Text("把蓝色块拖到这里")
    animated_box = ft.Container(
        width=90,
        height=60,
        bgcolor=ft.Colors.BLUE_300,
        border_radius=12,
        alignment=ft.alignment.center,
        animate=ft.Animation(450, ft.AnimationCurve.EASE_IN_OUT),
        content=ft.Text("动画"),
    )

    def log(message: str) -> None:
        output.value = f"事件输出：{message}"
        page.update()

    def open_dialog(_: ft.ControlEvent) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("AlertDialog"),
            content=ft.Text("这是 Material 弹窗组件。"),
            actions=[],
        )
        dialog.actions = [ft.TextButton("关闭", on_click=lambda __: page.close(dialog))]
        page.open(
            dialog,
        )

    def open_banner(_: ft.ControlEvent) -> None:
        banner = ft.Banner(
            bgcolor=ft.Colors.AMBER_100,
            leading=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED),
            content=ft.Text("Banner：顶部提示条。"),
            actions=[],
        )
        banner.actions = [ft.TextButton("关闭", on_click=lambda __: page.close(banner))]
        page.open(
            banner,
        )

    def open_bottom_sheet(_: ft.ControlEvent) -> None:
        bottom_sheet_body = ft.Column(
            tight=True,
            controls=[
                ft.Text("BottomSheet", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("底部弹出层。"),
            ],
        )
        bottom_sheet = ft.BottomSheet(
            ft.Container(
                padding=20,
                content=bottom_sheet_body,
            ),
        )
        bottom_sheet_body.controls.append(
            ft.ElevatedButton("关闭", on_click=lambda __: page.close(bottom_sheet)),
        )
        page.open(
            bottom_sheet,
        )

    def open_date_picker(_: ft.ControlEvent) -> None:
        page.open(
            ft.DatePicker(
                on_change=lambda event: log(f"DatePicker = {event.control.value}"),
            ),
        )

    def open_time_picker(_: ft.ControlEvent) -> None:
        page.open(
            ft.TimePicker(
                on_change=lambda event: log(f"TimePicker = {event.control.value}"),
            ),
        )

    def open_snack_bar(_: ft.ControlEvent) -> None:
        page.open(ft.SnackBar(ft.Text("SnackBar：短提示消息")))

    def toggle_animation(_: ft.ControlEvent) -> None:
        animated_box.width = 180 if animated_box.width == 90 else 90
        animated_box.bgcolor = (
            ft.Colors.PINK_300 if animated_box.width == 180 else ft.Colors.BLUE_300
        )
        animated_box.update()

    def on_reorder(event: ft.OnReorderEvent) -> None:
        if event.old_index is None or event.new_index is None:
            return
        controls = reorderable.controls
        item = controls.pop(event.old_index)
        controls.insert(event.new_index, item)
        reorderable.update()
        log(f"ReorderableListView: {event.old_index} -> {event.new_index}")

    def on_drag_accept(_: ft.DragTargetEvent) -> None:
        drag_target_text.value = "已接收 Draggable"
        drag_target_text.update()
        log("DragTarget 接收拖拽")

    def section(title: str, controls: ControlList) -> ft.Card:
        return ft.Card(
            elevation=1,
            margin=ft.margin.symmetric(horizontal=14, vertical=8),
            content=ft.Container(
                padding=16,
                content=ft.Column(
                    spacing=12,
                    controls=[
                        ft.Text(title, size=22, weight=ft.FontWeight.BOLD),
                        ft.Divider(),
                        ft.ResponsiveRow(
                            spacing=12,
                            run_spacing=12,
                            controls=[
                                ft.Container(
                                    content=control,
                                    col={"xs": 12, "md": 6, "xl": 4},
                                )
                                for control in controls
                            ],
                        ),
                    ],
                ),
            ),
        )

    def tile(title: str, control: ft.Control, note: str | None = None) -> ft.Container:
        body: ControlList = [ft.Text(title, weight=ft.FontWeight.BOLD), control]
        if note is not None:
            body.append(ft.Text(note, size=12, color=ft.Colors.GREY_700))
        return ft.Container(
            padding=12,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=12,
            bgcolor=ft.Colors.WHITE,
            content=ft.Column(spacing=8, controls=body),
        )

    def wrap_controls(controls: ControlList) -> ft.Row:
        return ft.Row(spacing=8, run_spacing=8, wrap=True, controls=controls)

    reorderable = ft.ReorderableListView(
        height=180,
        controls=[
            ft.ListTile(key=str(index), title=ft.Text(f"可排序项目 {index}"))
            for index in range(1, 5)
        ],
        on_reorder=on_reorder,
    )

    page.appbar = ft.AppBar(
        title=ft.Text("Flet 0.28.3 组件画廊"),
        center_title=False,
        actions=[
            ft.IconButton(
                ft.Icons.INFO_OUTLINE,
                tooltip="AppBar / IconButton",
                on_click=lambda _: log("AppBar action"),
            ),
            ft.PopupMenuButton(
                items=[
                    ft.PopupMenuItem(
                        text="PopupMenuItem A",
                        icon=ft.Icons.STAR,
                        on_click=lambda _: log("菜单 A"),
                    ),
                    ft.PopupMenuItem(
                        text="PopupMenuItem B",
                        checked=True,
                        on_click=lambda _: log("菜单 B"),
                    ),
                ],
            ),
        ],
    )
    page.navigation_bar = ft.NavigationBar(
        destinations=[
            ft.NavigationBarDestination(
                icon=ft.Icons.HOME_OUTLINED,
                selected_icon=ft.Icons.HOME,
                label="首页",
            ),
            ft.NavigationBarDestination(
                icon=ft.Icons.WIDGETS_OUTLINED,
                selected_icon=ft.Icons.WIDGETS,
                label="组件",
            ),
        ],
        on_change=lambda event: log(
            f"NavigationBar index = {event.control.selected_index}",
        ),
    )
    page.drawer = ft.NavigationDrawer(
        controls=[
            ft.NavigationDrawerDestination(
                icon=ft.Icons.HOME_OUTLINED,
                label="NavigationDrawer",
            ),
            ft.NavigationDrawerDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                label="设置",
            ),
        ],
    )
    page.floating_action_button = ft.FloatingActionButton(
        icon=ft.Icons.ADD,
        text="FAB",
        on_click=lambda _: log("FloatingActionButton"),
    )

    sections = [
        section(
            "基础显示与布局",
            [
                tile(
                    "Text / TextSpan",
                    ft.Text(
                        spans=[
                            ft.TextSpan("富文本 "),
                            ft.TextSpan(
                                "TextSpan",
                                style=ft.TextStyle(
                                    color=ft.Colors.BLUE,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                    ),
                ),
                tile(
                    "Icon / Image / CircleAvatar",
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.FAVORITE, color=ft.Colors.PINK),
                            ft.Image(
                                src="https://picsum.photos/80",
                                width=56,
                                height=56,
                            ),
                            ft.CircleAvatar(content=ft.Text("F")),
                        ],
                    ),
                ),
                tile(
                    "Container / Row / Column",
                    ft.Container(
                        bgcolor=ft.Colors.BLUE_50,
                        border_radius=8,
                        padding=10,
                        content=ft.Column(
                            [
                                ft.Text("Column"),
                                ft.Row(
                                    [
                                        ft.Chip(label=ft.Text("Row")),
                                        ft.Chip(label=ft.Text("Chip")),
                                    ],
                                ),
                            ],
                        ),
                    ),
                ),
                tile(
                    "Stack",
                    ft.Stack(
                        width=180,
                        height=80,
                        controls=[
                            ft.Container(
                                width=120,
                                height=60,
                                bgcolor=ft.Colors.GREEN_100,
                            ),
                            ft.Container(
                                left=40,
                                top=20,
                                width=120,
                                height=60,
                                bgcolor=ft.Colors.ORANGE_100,
                                content=ft.Text("Stack"),
                            ),
                        ],
                    ),
                ),
                tile(
                    "Card / Divider / VerticalDivider",
                    ft.Card(
                        content=ft.Container(
                            padding=10,
                            content=ft.Row(
                                [
                                    ft.Text("左"),
                                    ft.VerticalDivider(width=20),
                                    ft.Text("右"),
                                ],
                            ),
                        ),
                    ),
                ),
                tile(
                    "Placeholder",
                    ft.Placeholder(fallback_width=180, fallback_height=80),
                ),
            ],
        ),
        section(
            "输入、选择与表单",
            [
                tile(
                    "TextField",
                    ft.TextField(
                        label="TextField",
                        hint_text="请输入内容",
                        on_change=lambda e: log(f"TextField = {e.control.value}"),
                    ),
                ),
                tile(
                    "Dropdown",
                    ft.Dropdown(
                        label="Dropdown",
                        value="A",
                        options=[
                            ft.DropdownOption("A", text="选项 A"),
                            ft.DropdownOption("B", text="选项 B"),
                        ],
                        on_change=lambda e: log(f"Dropdown = {e.control.value}"),
                    ),
                ),
                tile(
                    "Checkbox / Switch",
                    ft.Column(
                        [
                            ft.Checkbox(
                                label="Checkbox",
                                value=True,
                                on_change=lambda e: log(
                                    f"Checkbox = {e.control.value}",
                                ),
                            ),
                            ft.Switch(
                                label="Switch",
                                value=True,
                                on_change=lambda e: log(f"Switch = {e.control.value}"),
                            ),
                        ],
                    ),
                ),
                tile(
                    "RadioGroup / Radio",
                    ft.RadioGroup(
                        value="one",
                        content=ft.Column(
                            [
                                ft.Radio(value="one", label="Radio 1"),
                                ft.Radio(value="two", label="Radio 2"),
                            ],
                        ),
                        on_change=lambda e: log(f"RadioGroup = {e.control.value}"),
                    ),
                ),
                tile(
                    "Slider / RangeSlider",
                    ft.Column(
                        [
                            ft.Slider(min=0, max=100, value=40, label="{value}"),
                            ft.RangeSlider(
                                min=0,
                                max=100,
                                start_value=20,
                                end_value=80,
                            ),
                        ],
                    ),
                ),
                tile(
                    "SegmentedButton",
                    ft.SegmentedButton(
                        segments=[
                            ft.Segment("day", label=ft.Text("日")),
                            ft.Segment("week", label=ft.Text("周")),
                            ft.Segment("month", label=ft.Text("月")),
                        ],
                        selected={"day"},
                        on_change=lambda e: log(
                            f"SegmentedButton = {e.control.selected}",
                        ),
                    ),
                ),
                tile(
                    "AutoComplete",
                    ft.AutoComplete(
                        suggestions=[
                            ft.AutoCompleteSuggestion(key="python", value="Python"),
                            ft.AutoCompleteSuggestion(key="flet", value="Flet"),
                        ],
                        on_select=lambda e: log(f"AutoComplete = {e.selection.value}"),
                    ),
                ),
                tile(
                    "SearchBar",
                    ft.SearchBar(
                        width=320,
                        bar_hint_text="SearchBar",
                        controls=[
                            ft.ListTile(title=ft.Text("搜索建议 1")),
                            ft.ListTile(title=ft.Text("搜索建议 2")),
                        ],
                    ),
                ),
            ],
        ),
        section(
            "按钮、菜单与反馈",
            [
                tile(
                    "Material Buttons",
                    wrap_controls(
                        [
                            ft.ElevatedButton("Elevated"),
                            ft.FilledButton("Filled"),
                            ft.FilledTonalButton("Tonal"),
                            ft.OutlinedButton("Outlined"),
                            ft.TextButton("Text"),
                            ft.IconButton(ft.Icons.THUMB_UP),
                        ],
                    ),
                ),
                tile(
                    "Button / MenuBar",
                    ft.Column(
                        [
                            ft.Button("通用 Button", on_click=lambda _: log("Button")),
                            ft.MenuBar(
                                controls=[
                                    ft.SubmenuButton(
                                        content=ft.Text("MenuBar"),
                                        controls=[
                                            ft.MenuItemButton(
                                                content=ft.Text("MenuItemButton"),
                                                on_click=lambda _: log(
                                                    "MenuItemButton",
                                                ),
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                tile(
                    "Dialog / Banner / BottomSheet",
                    wrap_controls(
                        [
                            ft.ElevatedButton("AlertDialog", on_click=open_dialog),
                            ft.ElevatedButton("Banner", on_click=open_banner),
                            ft.ElevatedButton(
                                "BottomSheet",
                                on_click=open_bottom_sheet,
                            ),
                        ],
                    ),
                ),
                tile(
                    "SnackBar / DatePicker / TimePicker",
                    wrap_controls(
                        [
                            ft.ElevatedButton("SnackBar", on_click=open_snack_bar),
                            ft.ElevatedButton("DatePicker", on_click=open_date_picker),
                            ft.ElevatedButton("TimePicker", on_click=open_time_picker),
                        ],
                    ),
                ),
                tile(
                    "Progress",
                    ft.Column(
                        [ft.ProgressBar(value=0.55), ft.ProgressRing(value=0.65)],
                    ),
                ),
                tile(
                    "HapticFeedback / SemanticsService",
                    ft.Text("服务型控件通常通过方法调用触发，移动端更常用。"),
                ),
            ],
        ),
        section(
            "列表、表格、导航与容器",
            [
                tile(
                    "ListView / ListTile",
                    ft.ListView(
                        height=150,
                        controls=[
                            ft.ListTile(
                                leading=ft.Icon(ft.Icons.LIST),
                                title=ft.Text(f"ListTile {i}"),
                                subtitle=ft.Text("subtitle"),
                            )
                            for i in range(1, 4)
                        ],
                    ),
                ),
                tile(
                    "GridView",
                    ft.GridView(
                        height=150,
                        runs_count=3,
                        max_extent=90,
                        child_aspect_ratio=1,
                        controls=[
                            ft.Container(
                                bgcolor=ft.Colors.BLUE_100,
                                alignment=ft.alignment.center,
                                content=ft.Text(str(i)),
                            )
                            for i in range(1, 7)
                        ],
                    ),
                ),
                tile(
                    "DataTable",
                    ft.DataTable(
                        columns=[
                            ft.DataColumn(ft.Text("列 A")),
                            ft.DataColumn(ft.Text("列 B")),
                        ],
                        rows=[
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text("A1")),
                                    ft.DataCell(ft.Text("B1")),
                                ],
                            ),
                            ft.DataRow(
                                cells=[
                                    ft.DataCell(ft.Text("A2")),
                                    ft.DataCell(ft.Text("B2")),
                                ],
                            ),
                        ],
                    ),
                ),
                tile(
                    "Tabs / Tab",
                    ft.Tabs(
                        tabs=[
                            ft.Tab(text="Tab 1", content=ft.Text("内容 1")),
                            ft.Tab(text="Tab 2", content=ft.Text("内容 2")),
                        ],
                        height=120,
                    ),
                ),
                tile(
                    "ExpansionTile / ExpansionPanelList",
                    ft.Column(
                        [
                            ft.ExpansionTile(
                                title=ft.Text("ExpansionTile"),
                                controls=[ft.ListTile(title=ft.Text("展开内容"))],
                            ),
                            ft.ExpansionPanelList(
                                controls=[
                                    ft.ExpansionPanel(
                                        header=ft.ListTile(
                                            title=ft.Text("ExpansionPanel"),
                                        ),
                                        content=ft.ListTile(
                                            title=ft.Text("Panel 内容"),
                                        ),
                                        expanded=True,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                tile(
                    "NavigationRail",
                    ft.NavigationRail(
                        selected_index=0,
                        label_type=ft.NavigationRailLabelType.ALL,
                        destinations=[
                            ft.NavigationRailDestination(
                                icon=ft.Icons.HOME_OUTLINED,
                                label="Home",
                            ),
                            ft.NavigationRailDestination(
                                icon=ft.Icons.SETTINGS_OUTLINED,
                                label="Settings",
                            ),
                        ],
                        height=160,
                    ),
                ),
                tile(
                    "SafeArea / SelectionArea",
                    ft.SafeArea(
                        content=ft.SelectionArea(
                            content=ft.Text("这段文字可选择复制。"),
                        ),
                    ),
                ),
                tile(
                    "Pagelet / View",
                    ft.Pagelet(
                        height=180,
                        appbar=ft.AppBar(title=ft.Text("Pagelet")),
                        content=ft.Container(
                            alignment=ft.alignment.center,
                            content=ft.Text("局部页面容器；View 用于路由页面栈。"),
                        ),
                    ),
                ),
            ],
        ),
        section(
            "图表",
            [
                tile(
                    "BarChart",
                    ft.BarChart(
                        height=180,
                        max_y=10,
                        bar_groups=[
                            ft.BarChartGroup(
                                x=0,
                                bar_rods=[
                                    ft.BarChartRod(
                                        from_y=0,
                                        to_y=8,
                                        width=18,
                                        color=ft.Colors.BLUE,
                                    ),
                                ],
                            ),
                            ft.BarChartGroup(
                                x=1,
                                bar_rods=[
                                    ft.BarChartRod(
                                        from_y=0,
                                        to_y=5,
                                        width=18,
                                        color=ft.Colors.GREEN,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
                tile(
                    "LineChart",
                    ft.LineChart(
                        height=180,
                        min_y=0,
                        max_y=10,
                        min_x=0,
                        max_x=4,
                        data_series=[
                            ft.LineChartData(
                                data_points=[
                                    ft.LineChartDataPoint(0, 2),
                                    ft.LineChartDataPoint(1, 6),
                                    ft.LineChartDataPoint(2, 4),
                                    ft.LineChartDataPoint(3, 9),
                                ],
                                color=ft.Colors.PINK,
                            ),
                        ],
                    ),
                ),
                tile(
                    "PieChart",
                    ft.PieChart(
                        height=180,
                        sections=[
                            ft.PieChartSection(40, title="40%", color=ft.Colors.BLUE),
                            ft.PieChartSection(30, title="30%", color=ft.Colors.GREEN),
                            ft.PieChartSection(30, title="30%", color=ft.Colors.ORANGE),
                        ],
                    ),
                ),
                tile(
                    "ChartAxis / ChartAxisLabel",
                    ft.Text(
                        "ChartAxis、ChartAxisLabel 用于配置 BarChart/LineChart 坐标轴。",
                    ),
                ),
            ],
        ),
        section(
            "动画、手势、拖拽与高级控件",
            [
                tile(
                    "AnimatedSwitcher",
                    ft.AnimatedSwitcher(
                        content=ft.Text("AnimatedSwitcher 会在 content 变化时过渡。"),
                        duration=500,
                    ),
                ),
                tile(
                    "Container animate",
                    ft.Column(
                        [
                            animated_box,
                            ft.ElevatedButton("切换动画", on_click=toggle_animation),
                        ],
                    ),
                ),
                tile(
                    "GestureDetector",
                    ft.GestureDetector(
                        content=ft.Container(
                            bgcolor=ft.Colors.PURPLE_100,
                            padding=20,
                            content=ft.Text("点击/双击/长按"),
                        ),
                        on_tap=lambda _: log("GestureDetector tap"),
                        on_double_tap=lambda _: log("GestureDetector double tap"),
                        on_long_press_start=lambda _: log(
                            "GestureDetector long press",
                        ),
                    ),
                ),
                tile(
                    "Draggable / DragTarget",
                    ft.Row(
                        [
                            ft.Draggable(
                                group="demo",
                                content=ft.Container(
                                    width=70,
                                    height=70,
                                    bgcolor=ft.Colors.BLUE,
                                    border_radius=8,
                                ),
                                content_feedback=ft.Container(
                                    width=70,
                                    height=70,
                                    bgcolor=ft.Colors.BLUE_200,
                                    border_radius=8,
                                ),
                            ),
                            ft.DragTarget(
                                group="demo",
                                on_accept=on_drag_accept,
                                content=ft.Container(
                                    width=150,
                                    height=70,
                                    bgcolor=ft.Colors.GREEN_100,
                                    border_radius=8,
                                    alignment=ft.alignment.center,
                                    content=drag_target_text,
                                ),
                            ),
                        ],
                    ),
                ),
                tile(
                    "Dismissible",
                    ft.Dismissible(
                        content=ft.ListTile(title=ft.Text("左右滑动我")),
                        background=ft.Container(bgcolor=ft.Colors.GREEN),
                        secondary_background=ft.Container(bgcolor=ft.Colors.RED),
                        on_dismiss=lambda _: log("Dismissible dismissed"),
                    ),
                ),
                tile("ReorderableListView", reorderable),
                tile(
                    "InteractiveViewer",
                    ft.InteractiveViewer(
                        width=260,
                        height=150,
                        min_scale=0.5,
                        max_scale=4,
                        content=ft.Image(src="https://picsum.photos/320/180"),
                    ),
                ),
                tile(
                    "ShaderMask / TransparentPointer",
                    ft.ShaderMask(
                        shader=ft.LinearGradient(
                            colors=[ft.Colors.PINK, ft.Colors.BLUE],
                        ),
                        content=ft.TransparentPointer(
                            content=ft.Text(
                                "渐变遮罩文字",
                                size=26,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ),
                    ),
                ),
                tile(
                    "WindowDragArea",
                    ft.WindowDragArea(
                        content=ft.Container(
                            bgcolor=ft.Colors.GREY_200,
                            padding=12,
                            content=ft.Text("桌面端可拖动窗口区域"),
                        ),
                    ),
                ),
            ],
        ),
        section(
            "Cupertino 风格组件",
            [
                tile(
                    "CupertinoButton",
                    wrap_controls(
                        [
                            ft.CupertinoButton("CupertinoButton"),
                            ft.CupertinoFilledButton("Filled"),
                        ],
                    ),
                ),
                tile(
                    "Cupertino 输入",
                    ft.Column(
                        [
                            ft.CupertinoTextField(
                                placeholder_text="CupertinoTextField",
                            ),
                            ft.CupertinoSlider(value=0.4),
                            ft.CupertinoSwitch(value=True),
                            ft.CupertinoCheckbox(value=True),
                            ft.CupertinoRadio(value="a"),
                        ],
                    ),
                ),
                tile(
                    "CupertinoPicker / TimerPicker",
                    ft.Text(
                        "CupertinoPicker、CupertinoDatePicker、CupertinoTimerPicker 适合在 Cupertino 弹窗或底部层里使用。",
                    ),
                ),
                tile(
                    "Cupertino App/Nav/List",
                    ft.Column(
                        [
                            ft.CupertinoAppBar(middle=ft.Text("CupertinoAppBar")),
                            ft.CupertinoNavigationBar(
                                selected_index=0,
                                destinations=[
                                    ft.NavigationBarDestination(
                                        icon=ft.Icons.HOME,
                                        label="Home",
                                    ),
                                    ft.NavigationBarDestination(
                                        icon=ft.Icons.SETTINGS,
                                        label="Settings",
                                    ),
                                ],
                            ),
                            ft.CupertinoListTile(title=ft.Text("CupertinoListTile")),
                        ],
                    ),
                ),
                tile(
                    "Cupertino Dialog",
                    wrap_controls(
                        [
                            ft.CupertinoButton(
                                "Alert",
                                on_click=lambda _: page.open(
                                    ft.CupertinoAlertDialog(
                                        title=ft.Text("CupertinoAlertDialog"),
                                        content=ft.Text("iOS 风格弹窗"),
                                        actions=[
                                            ft.CupertinoDialogAction(
                                                "关闭",
                                                on_click=lambda __: log(
                                                    "CupertinoDialogAction",
                                                ),
                                            ),
                                        ],
                                    ),
                                ),
                            ),
                            ft.CupertinoButton(
                                "ActionSheet",
                                on_click=lambda _: page.open(
                                    ft.CupertinoActionSheet(
                                        title=ft.Text("CupertinoActionSheet"),
                                        actions=[
                                            ft.CupertinoActionSheetAction(
                                                content=ft.Text("操作"),
                                            ),
                                        ],
                                        cancel=ft.CupertinoActionSheetAction(
                                            content=ft.Text("取消"),
                                        ),
                                    ),
                                ),
                            ),
                        ],
                    ),
                ),
                tile("Cupertino Activity", ft.CupertinoActivityIndicator(radius=14)),
                tile(
                    "Cupertino Context / Segmented",
                    ft.Column(
                        [
                            ft.CupertinoSlidingSegmentedButton(
                                controls=[ft.Text("A"), ft.Text("B")],
                                selected_index=0,
                            ),
                            ft.CupertinoSegmentedButton(
                                controls=[ft.Text("一"), ft.Text("二")],
                                selected_index=0,
                            ),
                            ft.CupertinoContextMenu(
                                content=ft.Text("长按上下文菜单"),
                                actions=[
                                    ft.CupertinoContextMenuAction(
                                        content=ft.Text("复制"),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ),
            ],
        ),
        section(
            "文件、Markdown 与其它说明",
            [
                tile(
                    "Markdown",
                    ft.Markdown("# Markdown\n- 支持 **粗体**\n- 支持 `code`"),
                ),
                tile(
                    "FilePicker",
                    ft.Column(
                        [
                            ft.Text(
                                "FilePicker 是 overlay 控件，需加入 page.overlay 后调用。",
                            ),
                            ft.ElevatedButton(
                                "示例占位",
                                on_click=lambda _: log(
                                    "FilePicker 需要在真实桌面/浏览器环境中打开",
                                ),
                            ),
                        ],
                    ),
                ),
                tile(
                    "AutofillGroup",
                    ft.AutofillGroup(
                        content=ft.Column(
                            [
                                ft.TextField(label="用户名"),
                                ft.TextField(label="密码", password=True),
                            ],
                        ),
                    ),
                ),
                tile(
                    "Semantics",
                    ft.Semantics(
                        label="可访问性标签",
                        button=True,
                        content=ft.ElevatedButton("可访问性按钮"),
                    ),
                ),
                tile(
                    "ShakeDetector",
                    ft.Text("ShakeDetector 主要用于移动端摇一摇事件。"),
                ),
                tile(
                    "FletApp / Page / AdaptiveControl",
                    ft.Text(
                        "FletApp、Page 是应用宿主；AdaptiveControl 是自适应控件基类/能力。",
                    ),
                ),
            ],
        ),
    ]

    page.add(
        ft.Column(
            controls=[
                ft.Container(
                    padding=16,
                    bgcolor=ft.Colors.BLUE_GREY_50,
                    content=ft.Column(
                        controls=[
                            ft.Text(
                                "Flet 自带组件概览",
                                size=30,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "当前项目固定依赖：flet[all] == 0.28.3。此 demo 覆盖公开 Control 类中的主要可视控件；部分服务型、宿主型、移动端传感器控件以说明形式展示。",
                            ),
                            output,
                        ],
                    ),
                ),
                *sections,
                ft.Container(height=72),
            ],
        ),
    )


if __name__ == "__main__":
    ft.app(target=main)
