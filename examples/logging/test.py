from assisipy import casu;
casu1 = casu.Casu('casu-002.rtc');
while 1:
	if casu1.get_ir_raw_value(casu.IR_F) > 15000:
		casu1.set_diagnostic_led_rgb(r=1);
	else:
		casu1.set_diagnostic_led_rgb(r=0);


