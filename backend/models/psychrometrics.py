# 檔案位置: backend/models/psychrometrics.py
import math

class PsychroModel:
    def __init__(self, p_atm_kpa=101.325):
        self.P_atm = p_atm_kpa

    def get_saturation_vapor_pressure(self, t_c):
        """[ASAE標準] 飽和水氣壓 Pws (kPa)"""
        T_k = t_c + 273.15
        if 0 <= t_c <= 200:
            C8, C9, C10 = -5.8002206E+03, 1.3914993E+00, -4.8640239E-02
            C11, C12, C13 = 4.1764768E-05, -1.4452093E-08, 6.5459673E+00
            ln_pws = (C8/T_k) + C9 + (C10*T_k) + (C11*T_k**2) + (C12*T_k**3) + (C13*math.log(T_k))
            return math.exp(ln_pws) / 1000.0
        elif t_c < 0:
            C1, C2 = -5.6745359E+03, 6.3925247E+00
            ln_pws = (C1/T_k) + C2
            return math.exp(ln_pws) / 1000.0
        return 0.001

    def get_partial_vapor_pressure(self, t_c, rh_percent):
        return self.get_saturation_vapor_pressure(t_c) * (rh_percent / 100.0)

    def get_vpd(self, t_c, rh_percent):
        pws = self.get_saturation_vapor_pressure(t_c)
        pw = pws * (rh_percent / 100.0)
        return pws - pw

    def get_dew_point(self, pw_kpa):
        """[ASAE 1999] 露點溫度"""
        c = 0.00145
        try: tmpV = math.log(c * pw_kpa * 1000)
        except: return -999
        A0, A1, A2 = 19.5322, 13.6626, 1.17678
        T_val = A0 + A1*tmpV + A2*(tmpV**2)
        return T_val - 273.15

    def get_enthalpy(self, t_c, w_kg_kg):
        """焓值 kJ/kg"""
        return 1.006 * t_c + w_kg_kg * (2501 + 1.805 * t_c)

    def get_humidity_ratio(self, pw_kpa):
        """絕對濕度 kg/kg"""
        return 0.62198 * pw_kpa / (self.P_atm - pw_kpa)