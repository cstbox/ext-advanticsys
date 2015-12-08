# CSTBox extension for AdvanticSys ModBus products support

This repository contains the code for the extension adding the support
for AdvanticSys ModBus based products in the [CSTBox framework](http://cstbox.cstb.fr). 

AdvanticSys products are industrial modules for Wireless ModBus. More details can be found
on their [Web site](http://http://www.advanticsys.com/).

The support comes in two forms :

  * product drivers generating CSTBox events from registers map readings
  * products definition files (aka metadata) driving the associated Web configuration editor
    pages

## Currently supported products

  * **DM-108**
      * ModBus wireless gateway

## Runtime dependencies

This extension requires the CSTBox core and ModBus support extension to be already installed.
