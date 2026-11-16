/// 폰 기능: 연락처 고르기, 지금 위치. 시험에서는 함수만 바꿔 끼운다.
library;

import 'package:flutter_native_contact_picker/flutter_native_contact_picker.dart';
import 'package:geolocator/geolocator.dart';

import 'store.dart';

typedef PickedContact = ({String name, String phone});
typedef Here = ({double lat, double lon});

class DeviceKit {
  /// 폰 연락처 앱이 열리고, 고른 사람의 이름·전화번호를 돌려준다(권한 필요 없음). 취소하면 null.
  static Future<PickedContact?> Function() pickContact = _pickContact;

  /// 지금 위치(GPS). 위치 권한을 처음 한 번 묻는다.
  static Future<Here> Function() here = _here;

  static Future<PickedContact?> _pickContact() async {
    final c = await FlutterNativeContactPicker().selectPhoneNumber();
    if (c == null) return null;
    final phone = c.selectedPhoneNumber ?? ((c.phoneNumbers?.isNotEmpty ?? false) ? c.phoneNumbers!.first : '');
    return (name: c.fullName ?? '', phone: phone.replaceAll(RegExp(r'[^0-9+\-]'), ''));
  }

  static Future<Here> _here() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw StoreError('폰의 위치(GPS)가 꺼져 있습니다. 켜고 다시 눌러 주세요.');
    }
    var p = await Geolocator.checkPermission();
    if (p == LocationPermission.denied) p = await Geolocator.requestPermission();
    if (p == LocationPermission.denied || p == LocationPermission.deniedForever) {
      throw StoreError('위치 권한이 없습니다. 설정 > 애플리케이션 > 진성현장 > 권한에서 위치를 허용해 주세요.');
    }
    try {
      final pos = await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(accuracy: LocationAccuracy.high, timeLimit: Duration(seconds: 15)));
      return (lat: pos.latitude, lon: pos.longitude);
    } catch (_) {
      final last = await Geolocator.getLastKnownPosition();
      if (last == null) throw StoreError('위치를 못 잡았습니다. 하늘이 보이는 곳에서 다시 눌러 주세요.');
      return (lat: last.latitude, lon: last.longitude);
    }
  }
}
