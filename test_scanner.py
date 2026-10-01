"""Synthetic rule/regression tests. Not trading-performance or course certification."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import numpy as np
import pandas as pd
import scanner as s


def bars(rows, start="2026-08-01"):
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                        index=pd.bdate_range(start, periods=len(rows)), dtype=float).assign(Volume=1000)


def zone(low=6.26, high=6.48):
    return {"i": 0, "departure_i": 1, "low": low, "high": high,
            "formed_at": "2026-08-01", "departure_atr": 1.8, "valid": True,
            "wick_breached": False, "retests": 0, "touch_bars": 0}


class LifecycleTests(unittest.TestCase):
    def test_bte_shaped_wick_recovery_warns(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.5,6.8,6.49,6.7],
                   [6.5,6.6,6.23,6.33],[6.4,6.6,6.3,6.5],[6.5,6.6,6.49,6.51]])
        z = s.zone_lifecycle(df, zone(), "demand", 4)
        self.assertTrue(z["valid"])
        self.assertTrue(z["wick_breached"])
        self.assertEqual(z["breach_extreme"], 6.23)
        self.assertEqual((z["retests"], z["touch_bars"]), (1,2))

    def test_completed_close_breach_does_not_recover(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.5,6.8,6.49,6.7],
                   [6.4,6.5,6.2,6.24],[6.5,6.8,6.5,6.7]])
        self.assertFalse(s.zone_lifecycle(df, zone(), "demand", 3)["valid"])

    def test_preconfirmation_breach_is_not_skipped(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.3,6.8,6.2,6.7]])
        self.assertTrue(s.zone_lifecycle(df, zone(), "demand", 1)["wick_breached"])

    def test_provisional_close_not_permanent_invalidation(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.5,6.8,6.49,6.7],[6.4,6.5,6.2,6.24]])
        z = s.zone_lifecycle(df, zone(), "demand", 1)
        self.assertTrue(z["valid"])
        self.assertTrue(z["wick_breached"])
        self.assertEqual(s.nearest_zone(6.24, [{**zone(), **z}], "demand"), (None,None))

    def test_supply_wick_is_symmetric(self):
        z = {**zone(7.0,7.23)}
        df = bars([[7.0,7.23,7,7.1],[6.9,6.99,6.7,6.8],[6.9,7.25,6.9,7.1]])
        info = s.zone_lifecycle(df,z,"supply",2)
        self.assertTrue(info["valid"])
        self.assertEqual(info["breach_extreme"],7.25)
        self.assertTrue(info["wick_breached"])

    def test_supply_close_invalidates(self):
        df = bars([[7.0,7.23,7,7.1],[6.9,6.99,6.7,6.8],[7.1,7.3,7.1,7.26]])
        self.assertFalse(s.zone_lifecycle(df,zone(7,7.23),"supply",2)["valid"])

    def test_separate_visits_and_daily_touches(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.5,6.8,6.49,6.7],
                   [6.5,6.6,6.3,6.5],[6.5,6.6,6.4,6.5],[6.5,6.6,6.3,6.5],
                   [6.6,6.8,6.5,6.7],[6.5,6.6,6.4,6.5]])
        z = s.zone_lifecycle(df,zone(),"demand",6)
        self.assertEqual((z["retests"],z["touch_bars"],z["max_consecutive_touch_bars"]),(2,4,3))

    def test_equal_boundary_is_touch_not_breach(self):
        df = bars([[6.3,6.5,6.26,6.48],[6.5,6.8,6.49,6.7],[6.4,6.5,6.26,6.3]])
        z = s.zone_lifecycle(df,zone(),"demand",2)
        self.assertFalse(z["wick_breached"])
        self.assertEqual(z["touch_bars"],1)


class PivotTests(unittest.TestCase):
    def test_not_knowable_until_right_bars_close(self):
        df = bars([[10,11,9,10],[11,12,10,11],[12,14,11,12],
                   [11,12,10,11],[10,11,9,10]])
        self.assertEqual(s.confirmed_pivots(df,3)["high"],[])
        pivot = s.confirmed_pivots(df,4)["high"][0]
        self.assertEqual((pivot["i"],pivot["known_i"],pivot["price"]),(2,4,14))

    def test_append_future_does_not_change_known_pivots(self):
        df = bars([[10,11,9,10],[11,12,10,11],[12,14,11,12],
                   [11,12,10,11],[10,11,9,10],[10,15,8,12],[12,16,11,14]])
        self.assertEqual(s.confirmed_pivots(df.iloc[:5],4),s.confirmed_pivots(df,4))

    def test_today_never_used_as_completed_confirmation(self):
        df = bars([[10,11,9,10]]*3,"2026-09-29")
        now = datetime(2026,10,1,23,0,tzinfo=timezone.utc)
        self.assertEqual(s.completed_index(df,now),1)

    def test_plateau_uses_last_equal_high(self):
        df = bars([[10,h,9,10] for h in [11,12,14,14,12,11]])
        self.assertEqual([p["i"] for p in s.confirmed_pivots(df,5)["high"]],[3])


class BounceTests(unittest.TestCase):
    def setUp(self):
        self.df = bars([[100,101,99.5,100]]*31)
        self.df.iloc[22,:4] = [100,100.2,98.5,99.5]
        self.df.iloc[23,:4] = [99.5,100.5,98.6,99.9]
        self.df.iloc[30,:4] = [102,105.4,101.5,105]
        self.z = {**zone(98,99),"i":15,"departure_i":16}
        self.pivots = {"high":[{"i":12,"known_i":14,"price":106.,"date":"2026-08-19"},
                                {"i":18,"known_i":20,"price":104.,"date":"2026-08-27"}],"low":[]}

    def test_provisional_break_is_only_early(self):
        b = s.demand_bounce_state(self.df,self.z,29,self.pivots,lookback=9)
        self.assertEqual(b["status"],"early")
        self.assertIsNone(b["swing_break_at"])
        self.assertGreater(b["confirmation_trigger"],b["swing_high"])

    def test_completed_close_break_of_lower_high(self):
        b = s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)
        self.assertEqual(b["status"],"swing_break")
        self.assertEqual(b["swing_high"],104.)
        self.assertGreater(b["confirmation_trigger"],104.)

    def test_simple_bounce_without_pivot_not_confirmed(self):
        b = s.demand_bounce_state(self.df,self.z,30,{"high":[],"low":[]},lookback=9)
        self.assertEqual(b["status"],"early")
        self.assertIsNone(b["confirmation_trigger"])

    def test_wick_above_pivot_not_close_break(self):
        self.df.iloc[30,:4] = [102,106,101.5,103]
        self.assertEqual(s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)["status"],"early")

    def test_breached_demand_not_clean_bounce(self):
        self.z["wick_breached"] = True
        self.assertEqual(s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)["status"],"none")

    def test_pivot_unknown_at_touch_not_used(self):
        self.pivots["high"][-1]["known_i"] = 24
        self.assertEqual(s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)["status"],"early")

    def test_recross_cancels_swing_break(self):
        self.df.iloc[28,:4] = [102,105.4,101.5,105]
        self.df.iloc[29,:4] = [103,104,101,103]
        self.df.iloc[30,:4] = [102,103.8,101.5,103.5]
        self.assertNotEqual(s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)["status"],"swing_break")

    def test_only_latest_visit_low_used(self):
        self.df.iloc[20,:4] = [100,100.5,98.1,99.8]
        self.df.iloc[21,:4] = [100,101,99.5,100]
        b = s.demand_bounce_state(self.df,self.z,30,self.pivots,lookback=9)
        self.assertEqual(b["bounce_pct"],round((105-98.5)/98.5*100,2))


class SafetyTests(unittest.TestCase):
    def test_strict_json_even_nan_inf_numpy(self):
        obj = s.json_safe({"nan":float("nan"),"inf":np.float64("inf"),"bool":np.bool_(True)})
        self.assertEqual(json.loads(json.dumps(obj,allow_nan=False)),{"nan":None,"inf":None,"bool":True})

    def test_flat_rsi(self):
        self.assertEqual(s.rsi(pd.Series([10.]*30)).iloc[-1],50)

    def test_up_only_rsi(self):
        self.assertEqual(s.rsi(pd.Series(range(1,31),dtype=float)).iloc[-1],100)

    def test_overlap_preserved_as_warning(self):
        self.assertTrue(s.zones_overlap(zone(146.21,159),zone(157.78,160.11)))
        self.assertFalse(s.zones_overlap(zone(6.26,6.48),zone(7,7.23)))

    def test_containing_zone_has_priority(self):
        first = zone(90,110)
        second = {**zone(99,99.9),"i":20}
        self.assertEqual(s.nearest_zone(100,[first,second],"demand")[0],first)

    def test_breached_supply_becomes_reference_and_next_intact_is_target(self):
        breached = {**zone(110,112), "i":10, "wick_breached":True,
                    "first_breach_at":"2026-09-22"}
        intact = {**zone(120,122), "i":20, "wick_breached":False}
        active, distance, ref = s.select_supply_view(100, [breached, intact])
        self.assertIs(active, intact)
        self.assertIs(ref, breached)
        self.assertAlmostEqual(distance, 20.0)

    def test_breached_supply_without_higher_intact_target_stays_reference_only(self):
        breached = {**zone(110,112), "i":10, "wick_breached":True,
                    "first_breach_at":"2026-09-22"}
        active, distance, ref = s.select_supply_view(100, [breached])
        self.assertIsNone(active)
        self.assertIsNone(distance)
        self.assertIs(ref, breached)

    def test_intact_nearest_supply_needs_no_reference(self):
        intact = {**zone(110,112), "i":10, "wick_breached":False}
        active, distance, ref = s.select_supply_view(100, [intact])
        self.assertIs(active, intact)
        self.assertAlmostEqual(distance, 10.0)
        self.assertIsNone(ref)

    def test_warning_score_cap(self):
        df = bars([[100,102,99,101]]*130)
        z = {**zone(99,101),"wick_breached":True,"first_breach_at":"2026-09-29"}
        with patch.object(s,"find_zones",return_value=([z],[])):
            row = s.score_row(df,datetime(2027,1,1,tzinfo=timezone.utc))
        self.assertLessEqual(row["score"],55)
        self.assertEqual(row["demand_bounce"],"none")
        self.assertTrue(any("boundary traded through" in w for w in row["warnings"]))

    def test_random_ohlc_smoke_and_invariants(self):
        rng = np.random.default_rng(5)
        close = 100+np.cumsum(rng.normal(0,1,400))
        op = np.r_[close[0],close[:-1]]
        df = pd.DataFrame({"Open":op,"High":np.maximum(op,close)+rng.random(400),
                           "Low":np.minimum(op,close)-rng.random(400),"Close":close,"Volume":1000},
                          index=pd.bdate_range("2024-01-01",periods=400))
        row = s.score_row(df,datetime(2026,10,1,tzinfo=timezone.utc))
        json.dumps(row,allow_nan=False)
        for z in [row["demand_zone"],row["supply_zone"]]:
            if z:
                self.assertLess(z["low"],z["high"])
                self.assertLessEqual(z["retests"],z["touch_bars"])
                self.assertGreater(z["confirmed_i"],z["i"])
                self.assertTrue(z["valid"])
        self.assertNotEqual(row["demand_bounce"],"confirmed")



class ZoneFormationTests(unittest.TestCase):
    def setUp(self):
        rows = [[101,102,100,101] for _ in range(45)]
        rows[24] = [102,104,101.5,103]
        rows[25] = [103,105,102.5,104]
        rows[26] = [103,104,101.5,102]
        rows[27] = [102,103,100.5,101]
        rows[30] = [99.7,100.5,99,100]
        rows[31] = [100.8,104.5,100.5,104]
        rows[32] = [104,106.5,103.5,106]
        for i in range(33,45):
            rows[i] = [106,107,105.5,106]
        self.df = bars(rows, "2025-01-01")

    def test_real_candidate_uses_confirmed_pivot(self):
        demand, _ = s.find_zones(self.df,44)
        candidate = next(z for z in demand if z["i"] == 30)
        self.assertEqual(candidate["broken_pivot_price"],105)
        self.assertEqual(candidate["confirmed_i"],32)
        self.assertEqual(candidate["formed_at"],"2025-02-12")

    def test_wick_break_does_not_create_zone(self):
        self.df.iloc[32,:4] = [104,106.5,103.5,104.5]
        self.df.iloc[33,:4] = [104,106.5,103.5,104.5]
        demand, _ = s.find_zones(self.df,44)
        self.assertFalse(any(z["i"] == 30 for z in demand))

    def test_zone_unavailable_before_confirmation(self):
        demand, _ = s.find_zones(self.df,31)
        self.assertFalse(any(z["i"] == 30 for z in demand))

    def test_supply_creation_is_symmetric(self):
        df = self.df.copy()
        df["Open"], df["Close"] = 200-self.df.Open, 200-self.df.Close
        df["High"], df["Low"] = 200-self.df.Low, 200-self.df.High
        _, supply = s.find_zones(df,44)
        candidate = next(z for z in supply if z["i"] == 30)
        self.assertEqual((candidate["low"],candidate["high"]),(100,101))

    def test_event_candle_is_rejected(self):
        self.df.iloc[30,:4] = [100,106,90,100]
        demand, _ = s.find_zones(self.df,44)
        self.assertFalse(any(z["i"] == 30 for z in demand))


if __name__ == "__main__":
    unittest.main()
