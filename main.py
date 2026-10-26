import asyncio
import flet as ft
from datetime import date, timedelta

from api import analyse_grocery_list, get_meal_plan
from progress import (
    load_progress, save_progress,
    on_daily_goal_met, xp_for_next_level,
    save_grocery_entry, update_meal_planner_streak, check_badges,
    ALL_BADGES, LEVEL_TITLES, LEVEL_THRESHOLDS,
)

# -----------------------------------------------------------
# FRONTEND COLORS
# ----------------------------------------------------------
BG      = "#000000"   # black
PRIMARY = "#1C9F75"   # teal green
WHITE   = "#FFFFFF"
DARK    = "#1A1A1A"
MUTED   = "#808080"

# -----------------------------------------------------------
# GROCERY ITEMS FOR THE DRAG-AND-DROP TRAY
# -----------------------------------------------------------
# Each item is just a plain dict: a display name (used in the actual
# grocery list sent to the API) and an emoji standing in for an image.
# Want a REAL image instead of an emoji? See the note at the very
# bottom of this file for how to swap this out for ft.Image.
GROCERY_ITEMS = [
    {"name": "Apple",     "emoji": "\U0001F34E"},
    {"name": "Banana",    "emoji": "\U0001F34C"},
    {"name": "Carrot",    "emoji": "\U0001F955"},
    {"name": "Broccoli",  "emoji": "\U0001F966"},
    {"name": "Grapes",    "emoji": "\U0001F347"},
    {"name": "Orange",    "emoji": "\U0001F34A"},
    {"name": "Tomato",    "emoji": "\U0001F345"},
    {"name": "Avocado",   "emoji": "\U0001F951"},
]

# -----------------------------------------------------------
# LOADING PROGRESS FROM PROGRESS.PY
# ----------------------------------------------------------
app_progress = load_progress()


async def main(page: ft.Page):
    page.title = "NutriQuest"
    page.bgcolor = BG
    page.scroll = ft.ScrollMode.AUTO
    page.window.width = 400
    page.window.height = 700
    page.window.resizable = False

    
    # shared dict is how the goals screen "remembers" the goals when
    state = {
        "goals": {"protein": "00", "carbs": "00", "fibre": "00"},
        "results": [],
        "not_found": [],
    }

    # =========================================================
    # GOALS SCREEN  
    # =========================================================
    def goals_view():
        protein_input = ft.TextField(
            label="Protein goal (g)", value=state["goals"]["protein"],
            color=WHITE, border_color=PRIMARY, width=320,
        )
        carbs_input = ft.TextField(
            label="Carbs goal (g)", value=state["goals"]["carbs"],
            color=WHITE, border_color=PRIMARY, width=320,
        )
        fibre_input = ft.TextField(
            label="Fibre goal (g)", value=state["goals"]["fibre"],
            color=WHITE, border_color=PRIMARY, width=320,
        )

        async def save_goals(e):
            state["goals"] = {
                "protein": protein_input.value,
                "carbs": carbs_input.value,
                "fibre": fibre_input.value,
            }
            await page.push_route("/input")

        return ft.View(
            route="/",
            bgcolor=BG,
            padding=50,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "NutriQuest", size=35, weight=ft.FontWeight.BOLD, color=PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Set Your Nutrition Goals!", size=20, color=WHITE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),
                protein_input,
                carbs_input,
                fibre_input,
                ft.Container(height=10),
                ft.Button(
                    "Save Goals",
                    bgcolor=PRIMARY, color=WHITE,
                    on_click=save_goals,
                    width=300,
                ),
            ],
        )

    # =========================================================
    # GROCERY INPUT SCREEN  ->  route "/input"
    # =========================================================

    def input_view():

        basket_items = []

        # This Text shows what's currently in the basket. We just
        # rewrite its .value every time something gets dropped in.
        basket_display = ft.Text(
            "Drag fruits & veggies here \U0001F447",
            color=MUTED, size=13, text_align=ft.TextAlign.CENTER,
        )

        error_text = ft.Text("", color="#FF5555", size=12)
        spinner = ft.ProgressRing(color=PRIMARY, visible=False, width=20, height=20)

        # Disabled until the basket has at least one item in it.
        analyze_button = ft.Button(
            "Analyze Nutrition", bgcolor=PRIMARY, color=WHITE, width=320,
            disabled=True,
        )

        # ---------------------------------------------------
        # THE DROP ZONE ("the basket")
        # ---------------------------------------------------
        # animate_scale=... is what makes this container capable of
        # animating: any time we change basket_box.scale afterwards,
        # Flet smoothly interpolates instead of jumping instantly.
        basket_box = ft.Container(
            content=ft.Column(
                [ft.Text("\U0001F6D2", size=40), basket_display],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            width=320,
            height=140,
            bgcolor=DARK,
            border=ft.Border.all(2, PRIMARY),  
            border_radius=16,
            alignment=ft.Alignment.CENTER,
            scale=1.0,
            animate_scale=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        )

        # This fires automatically when a Draggable is dropped onto
        # drop_zone (defined a bit further down).
        async def on_accept(e: ft.DragTargetEvent):
            # e.src is the actual Draggable control that got dropped
            # (Flet resolves it for us automatically). .data is the
            # little name-tag we attached to each draggable further
            # below (e.g. "Apple").
            item_name = e.src.data

            basket_items.append(item_name)
            basket_display.value = ", ".join(basket_items)
            basket_display.color = WHITE
            analyze_button.disabled = False
            error_text.value = ""

            # --- the "bounce" animation ---
            # Step 1: grow the basket a little...
            basket_box.scale = 1.08
            page.update()
            await asyncio.sleep(0.15)   # let the grow-animation actually play
            # Step 2: ...then shrink back to normal. Growing then
            # shrinking in quick succession is what reads as a "bounce".
            basket_box.scale = 1.0
            page.update()

        drop_zone = ft.DragTarget(
            group="grocery",     # must match the group= on the draggables below
            content=basket_box,
            on_accept=on_accept,
        )

        # ---------------------------------------------------
        # THE DRAGGABLE FRUIT/VEG TRAY
        # ---------------------------------------------------
        def make_draggable_item(item):
            # This is what the card looks like sitting in the tray.
            card = ft.Container(
                content=ft.Column(
                    [
                        ft.Text(item["emoji"], size=32),
                        ft.Text(item["name"], size=11, color=WHITE),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=2,
                ),
                width=70,
                height=70,
                bgcolor=DARK,
                border_radius=12,
                alignment=ft.Alignment.CENTER,
            )
            return ft.Draggable(
                group="grocery",           # only matching DragTargets accept this
                content=card,               # what sits in the tray
                content_feedback=ft.Container(   # what follows your finger/cursor while dragging
                    content=ft.Text(item["emoji"], size=32),
                    width=60, height=60, bgcolor=PRIMARY, border_radius=12,
                    alignment=ft.Alignment.CENTER,
                ),
                data=item["name"],          # the "name tag" on_accept reads later
            )

        fruit_tray = ft.Row(
            [make_draggable_item(item) for item in GROCERY_ITEMS],
            wrap=True,   # lets the cards flow onto a second line if they don't all fit
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
        )

        # ---------------------------------------------------
        # BUTTONS
        # ---------------------------------------------------
        async def go_to_results(e):
            if not basket_items:
                error_text.value = "Drag at least one item into the basket first."
                page.update()
                return

            error_text.value = ""
            spinner.visible = True
            analyze_button.disabled = True
            page.update()

            # analyse_grocery_list() expects one item per line, same as
            # before — we just build that string from the basket instead
            # of reading it from a TextField.
            raw_text = "\n".join(basket_items)

            try:
                results, not_found = await asyncio.to_thread(
                    analyse_grocery_list, raw_text
                )
                save_grocery_entry(app_progress, raw_text)
                state["results"] = results
                state["not_found"] = not_found
                await page.push_route("/results")
            except Exception as ex:
                error_text.value = f"Something went wrong: {ex}"
            finally:
                spinner.visible = False
                analyze_button.disabled = False
                page.update()

        analyze_button.on_click = go_to_results

        async def go_back_to_goals(e):
            await page.push_route("/")

        async def clear_basket(e):
            basket_items.clear()
            basket_display.value = "Drag fruits & veggies here \U0001F447"
            basket_display.color = MUTED
            analyze_button.disabled = True
            page.update()

        return ft.View(
            route="/input",
            bgcolor=BG,
            padding=24,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "NutriQuest", size=28, weight=ft.FontWeight.BOLD, color=PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Level 1 — Nutrition Newbie", size=14, color=MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),
                ft.Text("Pick your groceries:", color=WHITE, size=14),
                fruit_tray,
                ft.Container(height=14),
                drop_zone,
                ft.TextButton("Clear basket", on_click=clear_basket),
                ft.Row([analyze_button, spinner], alignment=ft.MainAxisAlignment.CENTER),
                error_text,
                ft.Button("Back", on_click=go_back_to_goals, width=320 , bgcolor=PRIMARY , color = WHITE),
            ],
        )
# =========================================================
    # RESULTS SCREEN -> route "/results"
    # =========================================================
    def results_view():
        results = state["results"]          # list of dicts: name, calories, protein, fat, carbs
        not_found_list = ", ".join(state["not_found"]) or "none"

        # ---------------------------------------------------
        # STEP 1: Add up totals across every item found.
        # We use sum() with a generator expression instead of a loop —
        # same result, less code. sum(x["protein"] for x in results)
        # reads as "add up the 'protein' value from every dict in results".
        # ---------------------------------------------------
        total_calories = sum(item["calories"] for item in results)
        total_protein  = sum(item["protein"]  for item in results)
        total_carbs    = sum(item["carbs"]    for item in results)
        total_fat      = sum(item["fat"]      for item in results)
        total_fibre = sum(item ["fibre"] for item in results)

        # ---------------------------------------------------
        # STEP 2: Pull the user's goals back out of state.
        # These come from TextFields on the goals screen, so they're
        # strings — we convert to float, with a safe fallback to 1
        # (not 0!) so we never divide by zero further down.
        # ---------------------------------------------------
        try:
            protein_goal = float(state["goals"]["protein"]) or 1
        except (ValueError, TypeError):
            protein_goal = 1

        try:
            carbs_goal = float(state["goals"]["carbs"]) or 1
        except (ValueError, TypeError):
            carbs_goal = 1

        try:
            fibre_goal = float(state["goals"]["fibre"]) or 1
        except(ValueError , TypeError):
            fibre_goal =1

        new_badges = []
        if results:
            protein_met = total_protein >= protein_goal
            carbs_met   = total_carbs   >= carbs_goal
            fibre_met = total_fibre >= fibre_goal

            # existing XP/streak/badge system — untouched
            new_badges += on_daily_goal_met(app_progress, protein_met=protein_met)

            # new, separate meal-planner unlock streak
            update_meal_planner_streak(app_progress, protein_met=protein_met, carbs_met=carbs_met , fibre_met=fibre_met)
            new_badges += check_badges(app_progress)   # re-check so meal_planner badge can fire same day
            save_progress(app_progress)

        meal_planner_unlocked = app_progress.get("meal_planner_unlocked", False)
        meal_planner_streak   = app_progress.get("meal_planner_streak", 0)


        # TODO (fibre): get_nutrition() doesn't return fibre yet, so we
        # can't compare against state["goals"]["fibre"] here. To enable
        # this, add "Fiber, total dietary" to the `nutrients.get(...)`
        # calls inside get_nutrition() in api.py, then add a
        # total_fibre / fibre_goal block here matching the pattern below.

        # ---------------------------------------------------
        # STEP 3: Build a little reusable progress row (label + bar +
        # numbers) so we're not repeating the same five lines twice.
        # min(1.0, ...) caps the bar at 100% even if they've gone over
        # the goal — ft.ProgressBar breaks visually above 1.0.
        # ---------------------------------------------------
        def progress_row(label, current, goal):
            fraction = min(1.0, current / goal) if goal else 0
            return ft.Column(
                [
                    ft.Row(
                        [
                            ft.Text(label, color=WHITE, size=13),
                            ft.Text(f"{current:.0f} / {goal:.0f} g", color=MUTED, size=12),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.ProgressBar(value=fraction, color=PRIMARY, bgcolor=DARK, height=8),
                ],
                spacing=4,
            )

        # ---------------------------------------------------
        # STEP 4: One card per grocery item, showing its own macros.
        # This is the "per-item detail" half of what you asked for.
        # ---------------------------------------------------
        def item_card(item):
            return ft.Container(
                content=ft.Column(
                    [
                        ft.Text(item["name"].title(), color=PRIMARY, size=15, weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Text(f"{item['calories']} kcal", color=WHITE, size=12),
                                ft.Text(f"P {item['protein']}g", color=WHITE, size=12),
                                ft.Text(f"C {item['carbs']}g", color=WHITE, size=12),
                                ft.Text(f"F {item['fat']}g", color=WHITE, size=12),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                    ],
                    spacing=6,
                ),
                bgcolor=DARK,
                border_radius=12,
                padding=12,
                width=320,
            )

        item_cards = [item_card(item) for item in results]

        # If nothing was found at all, show a friendly empty state
        # instead of an empty list with no explanation.
        if not item_cards:
            item_cards = [
                ft.Text(
                    "No items could be matched to nutrition data.",
                    color=MUTED, size=13, text_align=ft.TextAlign.CENTER,
                )
            ]

        async def go_back_to_input(e):
            await page.push_route("/input")

        meal_plan_spinner = ft.ProgressRing(color=PRIMARY, visible=False, width=20, height=20)
        meal_plan_error = ft.Text("", color="#FF5555", size=12, text_align=ft.TextAlign.CENTER)
        meal_plan_button = ft.Button(
            "Get My Meal Plan \U0001F37D️", bgcolor=PRIMARY, color=WHITE, width=320,
           )

        async def go_to_meal_plan(e):
            meal_plan_error.value = ""
            meal_plan_spinner.visible = True
            meal_plan_button.disabled = True
            page.update()
 
            try:
                plan_text = await asyncio.to_thread(
                    get_meal_plan,
                    app_progress.get("grocery_history", []),
                    state["goals"],
                )
                state["meal_plan"] = plan_text
                await page.push_route("/mealplan")
            except Exception as ex:
                meal_plan_error.value = f"Couldn't generate a meal plan: {ex}"
            finally:
                meal_plan_spinner.visible = False
                meal_plan_button.disabled = False
                page.update()
 
        meal_plan_button.on_click = go_to_meal_plan

        return ft.View(
            route="/results",
            bgcolor=BG,
            padding=24,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "Results", size=28, weight=ft.FontWeight.BOLD, color=PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"Found nutrition data for {len(results)} item(s).", color=WHITE,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"Not found: {not_found_list}", color=MUTED, size=12,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),

                # --- TOTALS vs GOALS ---
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text("Totals vs. Goals", color=WHITE, size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(f"{total_calories:.0f} kcal total", color=MUTED, size=12),
                            progress_row("Protein", total_protein, protein_goal),
                            progress_row("Carbs", total_carbs, carbs_goal),
                            progress_row("Fibre" , total_fibre , fibre_goal)
                        ],
                        spacing=10,
                    ),
                    bgcolor=DARK,
                    border_radius=16,
                    padding=16,
                    width=320,
                ),

                # --- MEAL PLANNER UNLOCK STATUS ---
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "🔓 Meal Planner Unlocked!" if meal_planner_unlocked
                                else f"🔒 Meal Planner — {meal_planner_streak}/3 day streak",
                                color=PRIMARY if meal_planner_unlocked else MUTED,
                                size=13,
                                text_align=ft.TextAlign.CENTER,
                            ),
                            ft.Text(
                                "Hit protein AND carbs 3 days in a row to unlock."
                                if not meal_planner_unlocked else
                                "Tap below to see your recommended meals.",
                                color=MUTED, size=11,
                                text_align=ft.TextAlign.CENTER,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=4,
                    ),
                    bgcolor=DARK,
                    border_radius=12,
                    padding=12,
                    width=320,
                ),

                *(
                    [
                        ft.Container(height=8),
                        ft.Row([meal_plan_button, meal_plan_spinner], alignment=ft.MainAxisAlignment.CENTER),
                        meal_plan_error,
                    ]
                    if meal_planner_unlocked else []
                ),

                ft.Container(height=14),
                ft.Text("Item breakdown:", color=WHITE, size=14),
                ft.Column(item_cards, spacing=10),

                ft.Container(height=10),
                ft.Button("Back", on_click=go_back_to_input, width=320 , bgcolor=PRIMARY , color = WHITE),
            ],
        )

    def meal_plan_view():
        # state["meal_plan"] was already filled in by go_to_meal_plan()
        # in results_view() BEFORE we navigated here, so there's nothing
        # to fetch on load — we just display it.
        plan_text = state.get("meal_plan", "No meal plan generated yet.")
 
        plan_display = ft.Text(
            plan_text, color=WHITE, size=13, selectable=True,
        )
 
        regen_spinner = ft.ProgressRing(color=PRIMARY, visible=False, width=20, height=20)
        regen_error = ft.Text("", color =PRIMARY, size=12, text_align=ft.TextAlign.CENTER)
        regen_button = ft.Button("Regenerate", width=320 , bgcolor=PRIMARY, color=WHITE)

        async def regenerate(e):
            regen_error.value = ""
            regen_spinner.visible = True
            regen_button.disabled = True
            page.update()

            try:
                new_plan = await asyncio.to_thread(
                    get_meal_plan,
                    app_progress.get("grocery_history", []),
                    state["goals"],
                )
                state["meal_plan"] = new_plan
                plan_display.value = new_plan   # update the text in place, no navigation needed
            except Exception as ex:
                regen_error.value = f"Couldn't generate a meal plan: {ex}"
            finally:
                regen_spinner.visible = False
                regen_button.disabled = False
                page.update()
 
        regen_button.on_click = regenerate

        async def go_back_to_results(e):
            await page.push_route("/results")

        return ft.View(
            route="/mealplan",
            bgcolor=BG,
            padding=24,
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "Your Meal Plan !", size=24, weight=ft.FontWeight.BOLD, color=PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(height=10),
                ft.Container(
                    content=plan_display,
                    bgcolor=DARK,
                    border_radius=16,
                    padding=16,
                    width=320,
                ),
                ft.Container(height=10),
                ft.Row([regen_button, regen_spinner], alignment=ft.MainAxisAlignment.CENTER),
                regen_error,
                ft.Container(height=10),
                ft.Button("Back to Results", on_click=go_back_to_results, width=320 , bgcolor=PRIMARY, color=WHITE),
            ],
        )
    
    

    # =========================================================
    # ROUTING
    # =========================================================
    def route_change(e=None):
        page.views.clear()
        page.views.append(goals_view())

        if page.route == "/input":
            page.views.append(input_view())

        if page.route == "/results":
            page.views.append(input_view())
            page.views.append(results_view())


        if page.route == "/mealplan":
            page.views.append(input_view())
            page.views.append(results_view())
            page.views.append(meal_plan_view())


        page.update()

    page.on_route_change = route_change
    route_change()


if __name__ == "__main__":
    ft.run(main)