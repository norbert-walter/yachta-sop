Programming (Flashing)
======================

	* Connect programmer/fixture (SWD/JTAG/ISP/UART; pinout per drawing)
	* Verify firmware package (version, checksum, release status)
	* Sequence: Erase → Program → Verify → Set option bytes/fuses → Write SN/UID → load calibration as required
	* Save log with SN, FW version, timestamp (Form E1, CSV export)
	* On failure: one retry permitted; otherwise NCR and analysis
