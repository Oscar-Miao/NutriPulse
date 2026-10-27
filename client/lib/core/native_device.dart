import 'package:flutter/services.dart';
import 'data.dart';

/// Android capabilities stay behind one platform boundary; pages contain no Kotlin UI.
class NativeDevice {
  static const channel = MethodChannel('nutripulse/device');
  Future<Json> settings() async =>
      object(await channel.invokeMethod('settings'));
  Future<void> configure(String url, String token) =>
      channel.invokeMethod('configure', {'url': url, 'token': token});
  Future<String?> read(String key) =>
      channel.invokeMethod<String>('read', {'key': key});
  Future<void> write(String key, String? value) =>
      channel.invokeMethod('write', {'key': key, 'value': value});
  Future<Uint8List?> photo(bool camera) =>
      channel.invokeMethod<Uint8List>('photo', {'camera': camera});
  Future<Json?> photoDraft() async {
    final value = await channel.invokeMethod('photoDraft');
    return value == null ? null : object(value);
  }

  Future<void> savePhotoDraft(Uint8List bytes, String key) =>
      channel.invokeMethod('savePhotoDraft', {'bytes': bytes, 'key': key});
  Future<void> clearPhotoDraft() => channel.invokeMethod('clearPhotoDraft');
  Future<Json> healthSamples({bool requestPermission = true}) async => object(
    await channel.invokeMethod('healthSamples', {
      'requestPermission': requestPermission,
    }),
  );
  Future<void> revokeHealth() => channel.invokeMethod('revokeHealth');
  Future<bool> saveFile(String name, Uint8List bytes, String mime) async =>
      await channel.invokeMethod<bool>('saveFile', {
        'name': name,
        'bytes': bytes,
        'mime': mime,
      }) ??
      false;
  Future<void> openUrl(String url) =>
      channel.invokeMethod('openUrl', {'url': url});
  Future<void> clearLocal(String category) =>
      channel.invokeMethod('clearLocal', {'category': category});
}
