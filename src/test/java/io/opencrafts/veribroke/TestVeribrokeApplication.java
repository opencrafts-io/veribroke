package io.opencrafts.veribroke;

import org.springframework.boot.SpringApplication;

public class TestVeribrokeApplication {

	public static void main(String[] args) {
		SpringApplication.from(VeribrokeApplication::main).with(TestcontainersConfiguration.class).run(args);
	}

}
