#include "InventoryRowName.hpp"
#include <iostream>
#include <string>
int main() {
    using RingedKnightInventory::valid_source_row_name;
    if(!valid_source_row_name(L"黑伤")||!valid_source_row_name(L"Tang")||!valid_source_row_name(L"黑伤_2"))return 1;
    for(auto invalid:{L"",L"黑伤\n",L"黑伤\"",L"黑伤'",L"黑伤,",L"黑伤)",L"黑伤\\",L"黑伤;",L"黑伤[",L"黑伤\x7f",L"黑伤\x202e"})
        if(valid_source_row_name(invalid))return 2;
    if(valid_source_row_name(std::wstring(97,L'剑')))return 3;
    const std::wstring embedded_nul(L"黑\0伤",3);
    if(valid_source_row_name(embedded_nul))return 4;
    std::cout<<"PASS native row-name validation: Chinese and ASCII source keys; controls, NUL, delimiters and oversized keys rejected\n";
}
