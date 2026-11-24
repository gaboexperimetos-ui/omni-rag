---
title: "Proyecto — Automatización casa"
tags: [proyectos, domotica, python, mqtt]
---

# Proyecto: Automatización de casa

Objetivo: luces, temperatura y sensores controlados desde el móvil.

## Hardware

- ESP32 en cada habitación (MQTT)
- Raspberry Pi 4 como broker (Mosquitto) + Home Assistant
- Sensores: temperatura (DS18B20), movimiento (PIR), luz (BH1750)
- Relés para luces y calefacción

## Software

- Firmware ESP32: MicroPython + umqtt.simple
- HA: automatizaciones YAML + Node-RED para lógicas complejas
- Backup: script diario a NAS (rsync + borg)

## Estado

- [x] Broker MQTT en Pi
- [x] 3 ESP32 flasheados y reportando
- [ ] Automatización "luz al entrar" en pasillo
- [ ] Curva de calefacción por habitación
- [ ] Dashboard móvil

Ver [[IA local]] para meter un modelo pequeño en la Pi que decida cuándo encender.