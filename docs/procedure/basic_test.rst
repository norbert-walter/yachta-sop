Basic electrical test
=====================

	* Visual inspection passed
	* Short/continuity test of power rails to GND (power supplay current limiter)
	* Power‑on with bench PSU (current limit power source 50 mA; typically start < 20  mA)
	* Verify reference voltages/regulators 3,3 V +/- 0,3 V
	* Check power supplay
		* 12V -> max 0,3 mA
		* 24V -> max 0,15 mA
		* Overvoltage > 26V -> on power supplay current limiter activ
	* Basic comms (UART) and programming interface check (USB login on PC)
	* Record results (Form D1)
	
Equipment
---------
	* Power source 30V/1A with current limiter
	* Programming adapter
	* Digital volt meter
	
Test Circuit
------------

.. image:: /pics/U5.png
             :scale: 30%
			 
Pic.: Test circuit
