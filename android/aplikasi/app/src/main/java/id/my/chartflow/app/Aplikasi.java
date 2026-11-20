package id.my.chartflow.app;

import android.app.Application;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

/** Menyimpan pesan galat bila aplikasi tertutup sendiri, agar bisa ditampilkan saat dibuka lagi. */
public class Aplikasi extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        final Thread.UncaughtExceptionHandler asal = Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
            try (PrintWriter w = new PrintWriter(new FileWriter(new File(getFilesDir(), "galat.txt")))) {
                e.printStackTrace(w);
            } catch (Throwable ignored) {
            }
            if (asal != null) asal.uncaughtException(t, e);
        });
    }
}
