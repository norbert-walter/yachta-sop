Programming (Flashing)
======================

	* Connect USB programmer bracket
		* UART communication
	* Verify firmware package (version V1.20, checksum, release status)
	* Programming sequence:
		* Web flashtool
		* USB-Connection
		* Erase → Program → Verify → Set option bytes/fuses → load defaults (Complete automatic sequence)
	* Save log with SN, FW version, timestamp (Form E1, CSV export)
	* On failure:
		* one retry permitted
		* otherwise NCR and analysis

Web Flashtool
-------------

The web flash tool allows you to transfer the firmware for the OBP60 to the device using a web browser via a USB connection. To do this, connect the OBP60 to a PC or laptop via the USB-C port and launch the Chrome or Edge web browser. The OBP60 has a built-in USB-to-serial converter for data transfer. The USB-C cable can only be used to transfer the firmware. Operating the device via USB is not possible.

.. note::
	Web browsers other than **Chrome** or **Edge** are not currently supported because the functionality for accessing a serial port is not implemented in other web browsers.
	
.. warning::
	Please note that the web flash tool can only be used with an OBP60 V2.1 that uses an **ESP32-S3 N16R8** processor and a **GDEY042T81** e-paper display. If you use other hardware, you will need to compile a customized firmware version for your hardware. Follow the instructions in the Compiling and Downloading section.
	
For the flashing process you need the following things:
	* Yachta PCB V2.1
	* USB programmer bracket
	* Power supplay 12V
	* PC mit Chrome- oder Edge-Browser

**1. Yachta PCB put into flash mode**
	
	
**2. Flashtool starten**

	Next, go to the `Online Flashtool`_ website.

	.. _Online Flashtool: https://norbert-walter.github.io/Windsensor_Yachta/flash_tool/esp_flash_tool.html
	
	.. image:: ../pics/Web_Flasher1.png
	   :scale: 50%
	Fig.: Home Web Flashtool

	Then press **Connect** and select the appropriate serial port. Depending on the operating system you're using, the ports are labeled differently.

	* **Windows:** USB JTAG/serial debug unit COMx
	* **Linux:** /dev/ttyACMx

	.. image:: ../pics/Serial_Connection_Win.png
	   :scale: 50%
	Fig.: Selecting the interface

.. note::
	Please note that other serial ports may still be in use in the system. Select the port that appears after connecting the OBP60 to the USB port. Do not use existing ports; they are already in use for another device.
	
**3. Transmit Firmware**
	.. image:: ../pics/Web_Flasher2.png
	   :scale: 50%
	Fig.: Start flashing process
	
	Start the installation process by selecting "INSTALL XXX FIRMWARE." A message will appear after the transfer is successful.
	
	.. image:: ../pics/Web_Flasher3.png
	   :scale: 50%
	Pic.: Transferring the firmware
	
**4. Starting Yachta PCB**
	Briefly disconnect the USB connection bracket. The firmware starts. After a short time, the LED on the microcontroller board (U2) should light up.